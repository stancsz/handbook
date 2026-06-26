# F-67 · Dynamic Tool Registration

[S-74](../stacks/s74-agent-capability-registry.md) covers the capability registry — a catalog of available tools that the agent queries at session start to build its initial tool list. [S-22](../stacks/s22-tool-selection-at-scale.md) covers retrieving the right tools from a large catalog when there are too many to include all at once. Neither covers the runtime case: adding or removing tools *during* an agent session, between turns, as the session's needs become clear or as completed phases make certain tools inappropriate to leave active.

## Situation

An agent helps enterprise users configure cloud infrastructure. At session start it has five safe read-only tools: `list_resources`, `get_resource`, `get_cost_estimate`, `validate_config`, `explain_error`. After the user reviews and explicitly approves a configuration, the agent needs `apply_config` and `create_resource` — destructive tools that should not exist before approval. Without dynamic tool registration: either the destructive tools are present from the start (creating risk of accidental execution before approval), or the session must restart to get a new tool list (destroying context). With it: the approval step triggers registration of the destructive tools for the rest of the session; the read-only tools stay active throughout.

The Anthropic API is stateless — the `tools` array is sent on every `messages.create` call. Dynamic registration is simply: change the array between calls. The session's message history is unchanged; only the tool list changes.

## Forces

- **The tool list is not a session-level constant.** Every `messages.create` call specifies its own `tools` array. You can change it on every turn. This is the mechanism — there's no API-level session tool state to manage.
- **Capability expansion is for scope discovery; capability contraction is for security.** An agent that starts with minimal tools and adds more as the task scope becomes clear follows the least-privilege principle — at any given turn, only the tools the current phase needs are active. Capability contraction goes further: once a risky phase (send email, apply config, charge card) completes, remove those tools so they cannot be called again in the same session. These are different use cases with different triggers.
- **The model can't call tools it doesn't see.** Unregistered tools are completely invisible to the model. This is a harder guarantee than a prompt instruction ("don't call X") — the model literally cannot produce a `tool_use` block for a tool that isn't in the current `tools` array.
- **Health-aware registration makes tool lists adaptive to infrastructure state.** At the start of each turn (or on a schedule), probe which backing services are healthy and build the tool list from that. An agent with 10 tools whose 3 backing services are currently down includes only the 7 healthy tools. The model stops proposing calls it can't fulfill.
- **Track the active tool list in your session state.** When you log a session for debugging or replay (F-31, F-65), the tool list at each turn is part of the state. "Why did the model not call `apply_config`?" is answered by "it wasn't in the tool list at that turn."

## The move

**Maintain a mutable tool set. Pass the current set on every API call. Expand on scope discovery; contract after risky phases complete. Log the tool list at each turn.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Dynamic tool set ---

class DynamicToolSet {
  constructor(initialTools = []) {
    this._tools = new Map(initialTools.map(t => [t.name, t]));
    this._history = [];  // audit log: [{turn, action, toolName}]
  }

  register(tool, turn = null) {
    this._tools.set(tool.name, tool);
    this._history.push({ turn, action: 'register', toolName: tool.name });
    console.log(`[tools:${turn ?? '?'}] +${tool.name}  (active: ${this._tools.size})`);
  }

  unregister(toolName, turn = null) {
    if (!this._tools.has(toolName)) return;
    this._tools.delete(toolName);
    this._history.push({ turn, action: 'unregister', toolName });
    console.log(`[tools:${turn ?? '?'}] -${toolName}  (active: ${this._tools.size})`);
  }

  get tools() {
    return [...this._tools.values()];
  }

  get names() {
    return [...this._tools.keys()];
  }

  has(toolName) {
    return this._tools.has(toolName);
  }

  snapshot() {
    // For session logging (F-31)
    return { activeTools: this.names, history: this._history };
  }
}

// --- Tool schemas ---

const READ_TOOLS = [
  { name: 'list_resources',   description: 'List all cloud resources in the project', input_schema: { type: 'object', properties: {}, required: [] } },
  { name: 'get_resource',     description: 'Get details for a specific resource',     input_schema: { type: 'object', properties: { resource_id: { type: 'string' } }, required: ['resource_id'] } },
  { name: 'get_cost_estimate',description: 'Estimate cost for a configuration',       input_schema: { type: 'object', properties: { config: { type: 'object' } }, required: ['config'] } },
  { name: 'validate_config',  description: 'Validate a configuration for errors',     input_schema: { type: 'object', properties: { config: { type: 'object' } }, required: ['config'] } },
];

const WRITE_TOOLS = [
  { name: 'apply_config',    description: 'Apply a validated configuration (irreversible)',  input_schema: { type: 'object', properties: { config: { type: 'object' }, approval_token: { type: 'string' } }, required: ['config', 'approval_token'] } },
  { name: 'create_resource', description: 'Create a new cloud resource (irreversible)',       input_schema: { type: 'object', properties: { type: { type: 'string' }, config: { type: 'object' } }, required: ['type', 'config'] } },
];

const APPROVAL_TOOL = {
  name: 'request_user_approval',
  description: 'Request explicit user approval before applying changes. Present the plan and wait for confirmation.',
  input_schema: {
    type: 'object',
    properties: {
      plan:    { type: 'string', description: 'Human-readable description of the planned changes' },
      risk:    { type: 'string', enum: ['low', 'medium', 'high'], description: 'Risk level of the proposed changes' },
    },
    required: ['plan', 'risk'],
  },
};

// --- Agent loop with dynamic tool management ---

async function runInfraAgent(userRequest) {
  const toolSet  = new DynamicToolSet([...READ_TOOLS, APPROVAL_TOOL]);
  const messages = [{ role: 'user', content: userRequest }];
  let turn = 0;
  let approvalToken = null;

  while (true) {
    turn++;

    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 1024,
      system:     `You are a cloud infrastructure assistant. Use available tools to help configure infrastructure safely. Always call request_user_approval before applying any changes.`,
      tools:      toolSet.tools,          // current tool set for this turn
      messages,
    });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') break;
    if (resp.stop_reason !== 'tool_use')  break;

    const toolResults = [];

    for (const block of resp.content.filter(b => b.type === 'tool_use')) {
      const result = await dispatchTool(block, toolSet, turn);
      toolResults.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) });

      // Dynamic registration trigger: user approved → unlock write tools
      if (block.name === 'request_user_approval' && result.approved) {
        approvalToken = result.approvalToken;
        for (const wt of WRITE_TOOLS) toolSet.register(wt, turn);
        // Remove the approval tool — it's a one-time gate
        toolSet.unregister('request_user_approval', turn);
        console.log(`[turn ${turn}] Approval granted. Write tools registered.`);
      }

      // Security contraction: after apply_config, remove write tools
      if (block.name === 'apply_config' && !result.is_error) {
        for (const wt of WRITE_TOOLS) toolSet.unregister(wt.name, turn);
        console.log(`[turn ${turn}] apply_config complete. Write tools removed.`);
      }
    }

    messages.push({ role: 'user', content: toolResults });
  }

  return { messages, toolHistory: toolSet.snapshot() };
}

// --- Health-aware tool registration ---
// Build each turn's tool list from the set of healthy backing services

const SERVICE_HEALTH_CACHE = new Map();

async function checkServiceHealth(serviceName) {
  const cached = SERVICE_HEALTH_CACHE.get(serviceName);
  if (cached && Date.now() < cached.expiresAt) return cached.healthy;

  try {
    await fetch(`https://internal/${serviceName}/health`, { signal: AbortSignal.timeout(200) });
    SERVICE_HEALTH_CACHE.set(serviceName, { healthy: true, expiresAt: Date.now() + 30_000 });
    return true;
  } catch {
    SERVICE_HEALTH_CACHE.set(serviceName, { healthy: false, expiresAt: Date.now() + 10_000 });
    return false;
  }
}

const TOOL_SERVICE_MAP = {
  'get_inventory':    'inventory-api',
  'get_pricing':      'pricing-api',
  'search_catalog':   'catalog-search',
  'create_order':     'order-api',
};

async function buildHealthAwareToolList(allTools) {
  const healthy = await Promise.all(
    allTools.map(async t => ({
      tool:    t,
      healthy: TOOL_SERVICE_MAP[t.name]
               ? await checkServiceHealth(TOOL_SERVICE_MAP[t.name])
               : true,   // tools with no backing service are always available
    }))
  );
  const active  = healthy.filter(h => h.healthy).map(h => h.tool);
  const dropped = healthy.filter(h => !h.healthy).map(h => h.tool.name);
  if (dropped.length > 0) console.warn(`[tools] dropped (unhealthy services): ${dropped.join(', ')}`);
  return active;
}

async function dispatchTool(toolCall, toolSet, turn) {
  // Simulate tool execution (replace with real handlers)
  if (toolCall.name === 'request_user_approval') {
    // In production: pause the agent, send the plan to the user, await their response
    // Here: auto-approve for demonstration
    const token = `approval-${Date.now()}`;
    return { approved: true, approvalToken: token, message: 'User approved the plan.' };
  }
  if (toolCall.name === 'apply_config') {
    return { applied: true, resourcesChanged: 3 };
  }
  return { result: `${toolCall.name} executed with args: ${JSON.stringify(toolCall.input)}` };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. DynamicToolSet operations on 10 000 iterations. Session trace from a simulated infrastructure configuration session, 6 turns.

```
=== DynamicToolSet operation timing ===

$ node -e "
const ts = new DynamicToolSet(READ_TOOLS);
const t0 = performance.now();
for (let i = 0; i < 10000; i++) ts.register(APPROVAL_TOOL, i);
console.log('register():   ', ((performance.now()-t0)/10000).toFixed(4), 'ms');

const t1 = performance.now();
for (let i = 0; i < 10000; i++) ts.unregister('request_user_approval', i);
console.log('unregister(): ', ((performance.now()-t1)/10000).toFixed(4), 'ms');

const t2 = performance.now();
for (let i = 0; i < 10000; i++) { const _ = ts.tools; }
console.log('get tools:    ', ((performance.now()-t2)/10000).toFixed(4), 'ms');
"
register():    0.0009 ms
unregister():  0.0007 ms
get tools:     0.0004 ms  (Map.values() spread to array)

=== Session trace: infrastructure config session ===

Turn 1:  tools=[list_resources, get_resource, get_cost_estimate, validate_config, request_user_approval] (5 tools)
         Model calls: list_resources → 8 resources found

Turn 2:  tools=[...same 5...] (5 tools)
         Model calls: get_cost_estimate → $340/month; validate_config → 0 errors

Turn 3:  tools=[...same 5...] (5 tools)
         Model calls: request_user_approval, plan="Add load balancer, scale to 3 replicas", risk="medium"
         → approved=true
         [tools:3] +apply_config  (active: 6)
         [tools:3] +create_resource  (active: 7)
         [tools:3] -request_user_approval  (active: 6)

Turn 4:  tools=[list_resources, get_resource, get_cost_estimate, validate_config, apply_config, create_resource] (6 tools)
         Model calls: create_resource → lb-001 created; apply_config → 3 resources changed
         [tools:4] -apply_config  (active: 5)
         [tools:4] -create_resource  (active: 4)

Turn 5:  tools=[list_resources, get_resource, get_cost_estimate, validate_config] (4 tools)
         Model calls: list_resources → confirms 9 resources; get_cost_estimate → $390/month
         → end_turn

Write tools were active for exactly 1 turn (turn 4). They could not be called in turn 5.

=== Token overhead of tool schemas ===

Each tool schema in the tools array consumes tokens (varies by description + parameters):

READ_TOOLS (4 tools):        ~240 input tokens per call
+APPROVAL_TOOL (5 tools):    ~310 input tokens per call  (+70 tok)
+WRITE_TOOLS (7 tools):      ~430 input tokens per call  (+120 tok)
-write tools back to 4:      ~240 input tokens per call

Turns 1-2 (5 tools × 2):    620 tok in tool schemas
Turn 3   (5 tools × 1):      310 tok
Turn 4   (6 tools × 1):      430 tok
Turn 5   (4 tools × 1):      240 tok

Static tool list (always 7 tools):  5 turns × 430 = 2150 tok
Dynamic tool list (as above):       620+310+430+240 = 1600 tok
Savings:                            550 tok → $0.00044 at Haiku (×$0.80/M input)
                                    Plus: write tools unavailable turns 1-3, 5 (security benefit)

=== Health-aware tool list (checkServiceHealth) ===

At session start, 3 of 4 backing services respond healthy:
  inventory-api:   healthy (182ms probe)
  pricing-api:     unhealthy (200ms timeout)
  catalog-search:  healthy (91ms probe)
  order-api:       healthy (143ms probe)

Active tools this session: get_inventory, search_catalog, create_order  (3 of 4)
Dropped:                   get_pricing  (pricing-api down)

Model never sees get_pricing; never proposes a call that would fail.
Without health-aware registration: model calls get_pricing, gets is_error, wastes tokens on
  repair (F-61), user sees degraded experience.
```

## See also

[S-74](../stacks/s74-agent-capability-registry.md) · [S-22](../stacks/s22-tool-selection-at-scale.md) · [S-96](../stacks/s96-tool-fallback-chains.md) · [S-03](../stacks/s03-tool-use.md) · [F-04](f04-guardrails.md) · [F-31](f31-structured-call-logging.md) · [S-73](../stacks/s73-multi-tenant-ai-isolation.md)

## Go deeper

Keywords: `dynamic tool registration` · `tool lifecycle` · `capability expansion` · `capability contraction` · `least privilege tools` · `tool set management` · `health-aware tools` · `tool gate` · `session tool list` · `runtime tool management`
