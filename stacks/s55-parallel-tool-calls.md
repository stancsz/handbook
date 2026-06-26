# S-55 · Parallel Tool Calls

When a model needs information from three independent sources, it doesn't have to ask for them one at a time. Most model APIs support returning multiple `tool_use` blocks in a single response. Execute those calls concurrently, return all results together, and the model synthesizes from complete information in one step. Serial tool calls convert tool RTTs into a sum; parallel tool calls convert them into the maximum. On a typical three-tool lookup that difference is 39% faster wall-clock time with no token overhead.

## Situation

An agent answering "What's the status of this customer's account?" makes three tool calls: `get_customer_profile`, `get_order_history`, and `get_account_balance`. In a serial agent loop, each call takes one turn — three generation steps, three round-trips, 555ms of tool latency. With parallel tool calls, the model returns all three `tool_use` blocks in one generation step; they execute concurrently; the slowest (340ms) sets the total. Total tool latency drops from 555ms to 340ms. Generation cost is the same; tool RTT is the only variable.

## Forces

- Independent reads are always parallelizable. If tool B doesn't need tool A's result as input, there is no reason to wait. Serial execution of independent tools is a default behavior, not a correctness requirement.
- The model decides whether to issue parallel calls. You can't force it to parallelize; you can make it more likely by structuring the prompt to ask for multiple pieces of information simultaneously ("look up the profile, order history, and balance") rather than one at a time. Fragmented requests beget serial responses.
- Side-effecting tools must not parallelize. Two concurrent writes to the same record create a race condition. Two concurrent charges to the same account are a bug. Always serialize tools that write, delete, charge, or send. Read-only tools are safe to parallelize.
- High fan-out risks rate limits. Five or more simultaneous API calls to the same downstream service can trigger rate limiting ([F-20](../forward-deployed/f20-rate-limits-and-retry.md)). Batch parallel calls in groups of 3–5.
- Token cost of parallelism is zero. Parallel tool calls come from a single generation step. The LLM doesn't generate more tokens because it issues three tool calls instead of one — the tool_use blocks are compact structured outputs. What changes is the number of LLM generation steps: parallel reduces it.

## The move

**Prompt the model to gather multiple pieces of information simultaneously. Handle `content` arrays with multiple `tool_use` blocks. Execute tool calls with `Promise.all`; return all results in one `tool` role message.**

**How the response looks when the model parallels:**

```js
// Model response content — multiple tool_use blocks in one message
{
  role: 'assistant',
  content: [
    {
      type: 'text',
      text: "I'll retrieve the profile, order history, and balance simultaneously."
    },
    {
      type: 'tool_use',
      id: 'tu_001',
      name: 'get_customer_profile',
      input: { customer_id: 'cust_abc123' }
    },
    {
      type: 'tool_use',
      id: 'tu_002',
      name: 'get_order_history',
      input: { customer_id: 'cust_abc123', limit: 5 }
    },
    {
      type: 'tool_use',
      id: 'tu_003',
      name: 'get_account_balance',
      input: { customer_id: 'cust_abc123' }
    }
  ]
}
```

**Execute concurrently; return all results together:**

```js
async function handleToolCalls(assistantMessage, tools) {
  const toolUseBlocks = assistantMessage.content.filter(b => b.type === 'tool_use');
  if (toolUseBlocks.length === 0) return null;

  // Check for side effects before parallelizing
  const hasSideEffects = toolUseBlocks.some(b => SIDE_EFFECTING_TOOLS.has(b.name));
  if (hasSideEffects) {
    // Serial execution for write/charge/send tools
    return executeSerial(toolUseBlocks, tools);
  }

  // Execute all read-only calls concurrently
  const results = await Promise.all(
    toolUseBlocks.map(async block => {
      const result = await tools[block.name](block.input);
      return {
        type: 'tool_result',
        tool_use_id: block.id,  // must match the id from the tool_use block
        content: JSON.stringify(result),
      };
    })
  );

  // Return all results in one user message — the model synthesizes from all of them
  return { role: 'user', content: results };
}

const SIDE_EFFECTING_TOOLS = new Set([
  'send_email', 'charge_card', 'write_file', 'delete_record', 'post_message'
]);
```

**Prompting for parallel calls.** The model is more likely to issue parallel tool calls when the user request naturally groups them:

```
Less likely to parallel:  "What's my account balance?"
More likely to parallel:  "Give me a full account overview — profile, recent orders, and balance."
```

**Dependency check before parallelizing:**

| Scenario | Execution |
|---|---|
| Tool B needs Tool A's result | Serial |
| Both tools write to the same record | Serial |
| Both tools are read-only, no shared state | Parallel |
| One tool has side effects | Serial (all of them, or after reads) |
| More than 5 simultaneous calls | Batch: 3–5 at a time |

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. RTT values are representative (120ms profile, 340ms order history, 95ms balance) based on typical internal service latencies. Token costs computed exactly at $3/M input, $15/M output. LLM turn count difference verified: parallel = 2 turns (decision + synthesis); serial = 4 turns (3 decisions + synthesis).

```
=== Parallel vs serial tool execution (3 tools) ===

Tool                     RTT
get_customer_profile     120ms
get_order_history        340ms
get_account_balance       95ms

Serial execution:   555ms  (sum of RTTs)
Parallel execution: 340ms  (slowest RTT only)
Latency saved:      215ms  (39% faster)

=== LLM turn cost ===
Serial (3 decision turns + synthesis): $5.54/k calls
Parallel (1 decision + synthesis):     $5.52/k calls

→ Token cost is essentially the same; the benefit is latency, not cost.
   At 1,000 calls/day: 215ms × 1,000 = 215 seconds of user wait time saved daily.
```

Parallel tool calls are the highest-ROI latency optimization available in the agent loop. They require no model change, no architecture change — only an orchestrator that executes multiple `tool_use` blocks concurrently instead of serially.

## See also

[S-35](s35-latency-budget.md) · [S-19](s19-agent-loop.md) · [S-03](s03-tool-use.md) · [S-05](s05-multi-agent-patterns.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md)

## Go deeper

Keywords: `parallel tool calls` · `concurrent tool execution` · `tool_use blocks` · `fan-out` · `Promise.all` · `agent loop latency` · `tool parallelism` · `multi-tool response` · `function calling`
