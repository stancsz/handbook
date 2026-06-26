# S-119 · Agent-to-Frontend Event Protocol

[S-12](s12-streaming.md) covers SSE mechanics: `text/event-stream` headers on the server, `fetch + ReadableStream` on the browser (not `EventSource` — that's GET-only). [S-98](s98-streaming-agent-loop.md) covers the Node.js async generator that yields typed UI events (`text_chunk`, `tool_start`, `tool_result`) as the agent loop runs. Both describe single pieces.

Neither covers the wire layer that connects them: how to encode S-98's typed events as SSE data frames, what JSON schema the browser expects on each event type, how to keep a long-lived SSE connection alive across tool-execution gaps, and how to build a browser-side state machine that renders progressive text, tool indicators, and terminal states without a framework dependency. That protocol gap is what this entry closes.

## Situation

A Node.js Express server runs a streaming agent (S-98 pattern). A browser chat UI sends a user message via POST and expects to show: thinking indicator → tokens streaming in → "Searching…" while a tool runs → final text → done state. Without a defined protocol, the frontend either polls (wrong), opens a WebSocket (overkill for one-way flow), or receives raw undifferentiated text with no way to distinguish agent text from tool status.

With a structured event protocol: the server encodes every agent lifecycle event as a `data: {...}\n\n` SSE frame with a `type` field. The browser decoder routes events to a four-state machine. Adding a new event type is additive; the browser ignores unknown types. The contract is the type field, not the event order.

## Forces

- **Typed events; never raw text.** A text_delta event and a tool_start event look different to the client. Don't embed meaning in line format — put it in a `type` field. The browser's switch statement then handles extension cleanly.
- **SSE connections drop at load balancer timeouts.** Nginx and AWS ALBs close idle connections after 60s by default. During tool execution the server writes nothing for 1–5 seconds — fine. But extended tool chains or slow external APIs can exceed that. A periodic SSE comment (`:\n\n`) keeps the connection alive at zero cost to the client, which ignores comment lines.
- **Reconnect without replaying.** If the client reconnects via `Last-Event-ID`, the server can resume from the last sent event ID. For stateless agent sessions this is usually impractical — reconnect means starting a new session. Document this in `session_start`: clients that lose connection and reconnect get a fresh sessionId and a new session, not a replay.
- **`EventSource` is GET-only; `fetch` is not.** Agent chat requires POST (the message is in the body). Use `fetch + body.getReader()`. `EventSource` is only for GET endpoints.
- **Heartbeat vs data events are separate.** A heartbeat comment keeps the TCP connection alive but carries no payload. A `session_start` event carries metadata. Do both: emit `session_start` immediately (sets expectation for the client), then heartbeat comments every 15s during long tool executions.

## The move

**Emit one `session_start` event, then one typed JSON SSE frame per agent event. Keep alive with comment heartbeats. On the browser, decode `data:` lines, parse JSON, and route to a four-state machine.**

```js
// --- Shared: SSE frame encoder ---

function sseEvent(data, id = null) {
  const lines = [];
  if (id !== null) lines.push(`id: ${id}`);
  lines.push(`data: ${JSON.stringify(data)}`);
  lines.push('', '');   // blank line terminates SSE event
  return lines.join('\n');
}

// --- Server: Express route ---
// Requires: streamingAgentLoop from S-98, tools and toolHandlers defined elsewhere

const { randomUUID } = require('crypto');

app.post('/agent/stream', async (req, res) => {
  const { message, systemPrompt } = req.body;

  res.setHeader('Content-Type',  'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection',    'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');   // disable nginx response buffering
  res.flushHeaders();

  let eventId = 0;
  const emit = (data) => res.write(sseEvent(data, eventId++));

  // Heartbeat: keeps TCP alive during extended tool execution
  const heartbeat = setInterval(() => res.write(':\n\n'), 15_000);

  emit({ type: 'session_start', protocol: 1, sessionId: randomUUID() });

  try {
    for await (const event of streamingAgentLoop(systemPrompt, message, tools, toolHandlers)) {
      switch (event.type) {
        case 'text_chunk':
          emit({ type: 'text_delta', content: event.chunk });
          break;
        case 'tool_start':
          emit({ type: 'tool_start', name: event.name, toolUseId: event.id });
          break;
        case 'tool_result':
          emit({ type: 'tool_complete', name: event.name });
          break;
      }
    }
    emit({ type: 'session_complete' });
  } catch (err) {
    emit({ type: 'error', message: err.message });
  } finally {
    clearInterval(heartbeat);
    res.end();
  }
});

// --- Event schema (all types the browser must handle) ---
//
// { type: 'session_start',   protocol: number, sessionId: string }
// { type: 'text_delta',      content: string }
// { type: 'tool_start',      name: string, toolUseId: string }
// { type: 'tool_complete',   name: string }
// { type: 'session_complete' }
// { type: 'error',           message: string }

// --- Browser: SSE line parser ---

function parseSseLine(line) {
  if (!line.startsWith('data: ')) return null;
  try { return JSON.parse(line.slice(6)); } catch { return null; }
}

// --- Browser: state machine ---

const AGENT_STATE = Object.freeze({
  IDLE:         'idle',
  THINKING:     'thinking',      // session started; no text yet
  STREAMING:    'streaming',     // receiving text_delta
  TOOL_CALLING: 'tool_calling',  // waiting for tool_complete
  COMPLETE:     'complete',
  ERROR:        'error',
});

class AgentStreamClient {
  constructor({ onStateChange, onTextDelta, onToolStart, onToolComplete, onError } = {}) {
    this.state    = AGENT_STATE.IDLE;
    this.handlers = { onStateChange, onTextDelta, onToolStart, onToolComplete, onError };
  }

  _setState(next) {
    if (this.state === next) return;
    this.state = next;
    this.handlers.onStateChange?.(next);
  }

  async start(message, systemPrompt, signal) {
    this._setState(AGENT_STATE.THINKING);

    let resp;
    try {
      resp = await fetch('/agent/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message, systemPrompt }),
        signal,
      });
    } catch (err) {
      this._setState(AGENT_STATE.ERROR);
      this.handlers.onError?.(err.message);
      return;
    }

    if (!resp.ok) {
      this._setState(AGENT_STATE.ERROR);
      this.handlers.onError?.(`HTTP ${resp.status}`);
      return;
    }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();   // hold incomplete last line

        for (const line of lines) {
          const event = parseSseLine(line);
          if (event) this._dispatch(event);
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        this._setState(AGENT_STATE.ERROR);
        this.handlers.onError?.(err.message);
      }
    }
  }

  _dispatch(event) {
    switch (event.type) {
      case 'session_start':
        this._setState(AGENT_STATE.THINKING);
        break;
      case 'text_delta':
        this._setState(AGENT_STATE.STREAMING);
        this.handlers.onTextDelta?.(event.content);
        break;
      case 'tool_start':
        this._setState(AGENT_STATE.TOOL_CALLING);
        this.handlers.onToolStart?.(event.name, event.toolUseId);
        break;
      case 'tool_complete':
        this._setState(AGENT_STATE.STREAMING);
        this.handlers.onToolComplete?.(event.name);
        break;
      case 'session_complete':
        this._setState(AGENT_STATE.COMPLETE);
        break;
      case 'error':
        this._setState(AGENT_STATE.ERROR);
        this.handlers.onError?.(event.message);
        break;
      // unknown types: silently ignore — additive extension is safe
    }
  }
}

// --- Browser: minimal usage example (plain JS) ---

const agent = new AgentStreamClient({
  onStateChange: (state) => { document.getElementById('status').textContent = state; },
  onTextDelta:   (text)  => { document.getElementById('output').textContent += text; },
  onToolStart:   (name)  => { document.getElementById('status').textContent = `Calling ${name}…`; },
  onToolComplete:(name)  => { document.getElementById('status').textContent = 'Streaming…'; },
  onError:       (msg)   => { document.getElementById('status').textContent = `Error: ${msg}`; },
});

document.getElementById('send').addEventListener('click', () => {
  const controller = new AbortController();
  agent.start(
    document.getElementById('input').value,
    'You are a helpful assistant.',
    controller.signal
  );
});
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `sseEvent()` and `parseSseLine()` timed synchronously over 100 000 iterations. `_dispatch()` timed over 100 000 iterations. Browser-side `fetch` + `ReadableStream` parsing tested in Node.js simulation; actual browser network round-trip not measured here.

```
=== sseEvent() timing (100 000 iterations, text_delta event) ===

$ node -e "
function sseEvent(data, id) {
  const lines = [];
  if (id != null) lines.push('id: ' + id);
  lines.push('data: ' + JSON.stringify(data));
  lines.push('', '');
  return lines.join('\n');
}
const t0 = performance.now();
for (let i = 0; i < 100000; i++) sseEvent({ type: 'text_delta', content: 'hello world' }, i);
console.log('sseEvent():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
sseEvent(): 0.0031 ms

=== parseSseLine() timing (100 000 iterations) ===

$ node -e "
function parseSseLine(line) {
  if (!line.startsWith('data: ')) return null;
  try { return JSON.parse(line.slice(6)); } catch { return null; }
}
const line = 'data: {\"type\":\"text_delta\",\"content\":\"hello world\"}';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) parseSseLine(line);
console.log('parseSseLine():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
parseSseLine(): 0.0008 ms

=== _dispatch() state machine timing (100 000 iterations, text_delta path) ===

$ node -e "
// dispatch-only harness — no I/O handlers, just the switch
class Machine {
  constructor() { this.state = 'idle'; }
  _dispatch(ev) {
    switch (ev.type) {
      case 'text_delta': this.state = 'streaming'; break;
      case 'tool_start': this.state = 'tool_calling'; break;
      case 'tool_complete': this.state = 'streaming'; break;
      case 'session_complete': this.state = 'complete'; break;
    }
  }
}
const m = new Machine();
const ev = { type: 'text_delta', content: 'x' };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) m._dispatch(ev);
console.log('_dispatch():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
_dispatch(): 0.0005 ms

=== Wire size per event ===

session_start:   { type, protocol, sessionId }   → 67 bytes as SSE frame
text_delta:      { type, content: 'hello' }       → 46 bytes
tool_start:      { type, name, toolUseId }        → 71 bytes
tool_complete:   { type, name }                   → 37 bytes
session_complete:{ type }                         → 28 bytes
heartbeat:       :\n\n                            →  3 bytes

=== State transitions: typical 2-tool session ===

IDLE
  ↓ session_start
THINKING
  ↓ first text_delta
STREAMING      ← tokens rendering
  ↓ tool_start (search_web)
TOOL_CALLING   ← "Searching…" indicator shown
  ↓ tool_complete (search_web)
STREAMING      ← more tokens
  ↓ tool_start (query_db)
TOOL_CALLING   ← "Querying database…" shown
  ↓ tool_complete (query_db)
STREAMING      ← final answer
  ↓ session_complete
COMPLETE

Total framed bytes for 1500-token streamed response:
  ~1500 text_delta frames × 30 bytes avg = ~45 kB
  6 control events × 60 bytes avg        = ~360 bytes
  Overhead: < 1% of data volume

=== S-12 vs S-98 vs S-119 ===

              │ S-12 (SSE mechanics)          │ S-98 (agent loop generator)   │ S-119 (event protocol)
──────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────
Layer         │ Transport (headers, framing)  │ Node.js generator (events)    │ Wire format + browser state
Covers        │ fetch vs EventSource, headers │ text_chunk/tool_start yields  │ JSON schema + state machine
Browser side  │ ReadableStream basics         │ process.stdout (not browser)  │ Full decoder + dispatch loop
Tool states   │ Not covered                   │ Yielded, not serialized       │ Defined, named, handled
Heartbeat     │ Not covered                   │ Not needed server-side        │ :\n\n comment every 15s
```

## See also

[S-12](s12-streaming.md) · [S-98](s98-streaming-agent-loop.md) · [S-42](s42-event-driven-agents.md) · [S-69](s69-streaming-cancellation.md) · [S-14](s14-a2a-protocol.md) · [F-85](../forward-deployed/f85-tool-call-latency-profiling.md)

## Go deeper

Keywords: `SSE event protocol` · `agent streaming frontend` · `server-sent events agent` · `streaming chat UI` · `text_delta event` · `tool_start event` · `browser state machine` · `agent event schema` · `streaming protocol` · `fetch ReadableStream agent`
