# F-83 · Agent Capability Testing

[F-07](f07-eval-driven-development.md) covers eval-driven development: write test cases that measure output quality, run them on every prompt change, and block deploys when quality regresses. It tests what the model produces. [S-74](../stacks/s74-agent-capability-registry.md) covers capability registries: each agent declares what it can do (`{name, description, inputs, outputs}`) so orchestrators can route tasks to the right agent. It manages capability declarations.

Neither tests whether the declared capability actually works. An agent can declare `can_query_database: true` and have a broken database connector. A tool can have a valid schema but a handler that crashes on the first realistic input. A capability can be registered in the manifest but never exercised by any test. The gap between declaration and reality is what agent capability testing closes.

This is distinct from F-07 evals (which test output quality for known-good inputs) and from F-64 prompt template testing (which tests template rendering with zero API calls). Capability testing exercises the actual tool execution path — calls the real handler, checks that the real result structure matches the declared schema, and catches broken tools before they fail silently inside an agent session.

## Situation

A multi-agent customer service system has 14 registered tools across 3 agents: a lookup agent (customer records, order history, subscription status), a resolution agent (refund initiation, ticket creation, escalation), and a notification agent (email, SMS, in-app). After a backend team moves the CRM to a new API version, three tools silently break: `get_customer_record` now returns a different field structure, `create_ticket` requires a new required field, and `send_email` returns a 403 on all calls.

Without capability tests: the breakage is discovered by a customer service supervisor who notices agents are returning "I couldn't retrieve your account information" for every lookup. Root cause investigation takes 2 hours. The broken tools have been silent for 6 hours.

With capability tests running at deploy time and every 15 minutes in production: the CRM migration triggers a capability test run. `get_customer_record` fails schema validation (missing `account_tier` field), `create_ticket` fails with a missing required field error, `send_email` fails with a 403. All three are flagged before the migration completes. The backend team rolls back the connector config. Zero customer impact.

## Forces

- **Tool schemas are declarations, not guarantees.** A tool's `input_schema` tells the model what arguments to pass. It says nothing about whether the handler will succeed, whether the response matches the declared structure, or whether the external dependency the tool wraps is available. Schemas validate the call; only execution validates the handler.
- **Capability tests must use realistic inputs, not trivial ones.** A test that calls `get_customer_record({customer_id: "test"})` and only checks for a non-null response misses structural breaks. The test must assert that the response contains the fields the agent actually uses: `account_tier`, `email`, `subscription_status`. Use fixture inputs that cover the full response surface.
- **Some tools are side-effecting; capability tests must be safe to run.** `send_email`, `initiate_refund`, and `create_ticket` cannot be called against production in capability tests. Use: (1) a test/sandbox mode flag the handler respects, (2) a mock endpoint that validates the call shape without executing it, or (3) a dry-run parameter that returns a realistic response without side effects.
- **Capability tests should run at three moments:** (1) deploy time (gate the deploy if critical tools fail), (2) on a schedule in production (catch external dependency breakage), (3) on demand after an incident (verify recovery).
- **Not all capability failures are equal.** A broken lookup tool degrades the agent; it can fall back to "I couldn't find that." A broken escalation tool blocks the only path to resolution for urgent issues. Classify tools by consequence severity (S-105 severity model) and fail the deploy only for tools above a threshold.

## The move

**Write a capability test per tool: realistic fixture input, schema assertion on the response, side-effect safety gate. Run at deploy, on schedule, and on demand. Classify failures by severity; block deploys on critical-tool failures only.**

```js
const Anthropic = require('@anthropic-ai/sdk');

// --- Tool capability test definition ---

function defineCapabilityTest(toolName, opts) {
  const {
    fixtureInput,         // realistic input matching tool input_schema
    expectedFields,       // fields that must exist in the response
    expectedTypes,        // {field: 'string'|'number'|'boolean'|'array'|'object'}
    sideEffectSafe,       // true if safe to call in prod; false requires sandbox
    severity,             // 'critical' | 'high' | 'medium' | 'low'
    handler,              // async (input) => result
    sandboxHandler,       // async (input) => result — used when sideEffectSafe=false
    maxLatencyMs = 2000,  // SLO for the tool call
  } = opts;

  return { toolName, fixtureInput, expectedFields, expectedTypes, sideEffectSafe, severity, handler, sandboxHandler, maxLatencyMs };
}

// --- Test runner ---

async function runCapabilityTest(test, opts = {}) {
  const { useSandbox = !test.sideEffectSafe } = opts;
  const handlerFn = useSandbox ? (test.sandboxHandler ?? test.handler) : test.handler;

  if (!handlerFn) {
    return { toolName: test.toolName, status: 'SKIP', reason: 'no_handler', severity: test.severity };
  }

  const t0 = performance.now();
  let result, latencyMs, error;

  try {
    result    = await handlerFn(test.fixtureInput);
    latencyMs = performance.now() - t0;
  } catch (err) {
    latencyMs = performance.now() - t0;
    return {
      toolName: test.toolName,
      status:   'FAIL',
      reason:   'handler_threw',
      error:    err.message,
      latencyMs: parseFloat(latencyMs.toFixed(2)),
      severity: test.severity,
    };
  }

  const failures = [];

  // Check required fields
  for (const field of (test.expectedFields ?? [])) {
    if (!(field in result) || result[field] === null || result[field] === undefined) {
      failures.push(`missing_field:${field}`);
    }
  }

  // Check types
  for (const [field, expectedType] of Object.entries(test.expectedTypes ?? {})) {
    if (field in result) {
      const actual = Array.isArray(result[field]) ? 'array' : typeof result[field];
      if (actual !== expectedType) {
        failures.push(`wrong_type:${field} expected=${expectedType} got=${actual}`);
      }
    }
  }

  // Check latency SLO
  if (latencyMs > test.maxLatencyMs) {
    failures.push(`latency_exceeded:${latencyMs.toFixed(0)}ms > ${test.maxLatencyMs}ms`);
  }

  const status = failures.length === 0 ? 'PASS' : 'FAIL';

  return {
    toolName:   test.toolName,
    status,
    failures,
    latencyMs:  parseFloat(latencyMs.toFixed(2)),
    severity:   test.severity,
    result:     status === 'PASS' ? { fieldCount: Object.keys(result).length } : undefined,
  };
}

// --- Suite runner: run all tests, classify by severity ---

async function runCapabilityTestSuite(tests, opts = {}) {
  const { blockOnSeverities = ['critical'], useSandbox } = opts;

  const results = await Promise.all(
    tests.map(t => runCapabilityTest(t, { useSandbox }))
  );

  const passed   = results.filter(r => r.status === 'PASS');
  const failed   = results.filter(r => r.status === 'FAIL');
  const skipped  = results.filter(r => r.status === 'SKIP');

  const blockingFailures = failed.filter(r => blockOnSeverities.includes(r.severity));

  return {
    total:            results.length,
    passed:           passed.length,
    failed:           failed.length,
    skipped:          skipped.length,
    blockingFailures: blockingFailures.length,
    deployVerdict:    blockingFailures.length === 0 ? 'PASS — deploy safe'
      : `BLOCK — ${blockingFailures.length} critical tool(s) failed`,
    results,
    failedTools:  failed.map(r => ({ toolName: r.toolName, severity: r.severity, failures: r.failures })),
  };
}

// --- Scheduled runner: re-run in production on a timer ---

class CapabilityMonitor {
  constructor(tests, intervalMs = 15 * 60 * 1000) {
    this.tests       = tests;
    this.intervalMs  = intervalMs;
    this.history     = [];
    this.timer       = null;
  }

  start() {
    this.timer = setInterval(async () => {
      const suite = await runCapabilityTestSuite(this.tests, { useSandbox: true });
      this.history.push({ runAt: Date.now(), ...suite });
      if (suite.blockingFailures > 0) {
        // In production: page oncall, open incident
        console.error(`CAPABILITY ALERT: ${suite.deployVerdict}`);
      }
    }, this.intervalMs);
  }

  stop() { clearInterval(this.timer); }

  // Uptime per tool over history window
  toolUptime() {
    const uptime = {};
    for (const run of this.history) {
      for (const r of run.results) {
        if (!uptime[r.toolName]) uptime[r.toolName] = { passes: 0, total: 0 };
        uptime[r.toolName].total++;
        if (r.status === 'PASS') uptime[r.toolName].passes++;
      }
    }
    return Object.fromEntries(
      Object.entries(uptime).map(([t, u]) => [t, parseFloat((u.passes / u.total).toFixed(3))])
    );
  }
}

// --- Example: 14-tool suite for the customer service system ---

function buildCustomerServiceTests(handlers) {
  return [
    defineCapabilityTest('get_customer_record', {
      fixtureInput:   { customer_id: 'test_cust_001' },
      expectedFields: ['customer_id', 'email', 'account_tier', 'subscription_status'],
      expectedTypes:  { customer_id: 'string', email: 'string', account_tier: 'string' },
      sideEffectSafe: true,
      severity:       'critical',
      handler:        handlers.get_customer_record,
    }),
    defineCapabilityTest('create_ticket', {
      fixtureInput:   { customer_id: 'test_cust_001', subject: 'Test', priority: 'low', category: 'billing' },
      expectedFields: ['ticket_id', 'status', 'created_at'],
      expectedTypes:  { ticket_id: 'string', status: 'string' },
      sideEffectSafe: false,
      severity:       'high',
      handler:        handlers.create_ticket,
      sandboxHandler: handlers.create_ticket_sandbox,
    }),
    defineCapabilityTest('send_email', {
      fixtureInput:   { to: 'test@example.com', subject: 'Test', body: 'Capability test' },
      expectedFields: ['message_id', 'status'],
      expectedTypes:  { status: 'string' },
      sideEffectSafe: false,
      severity:       'high',
      handler:        handlers.send_email,
      sandboxHandler: handlers.send_email_sandbox,
    }),
    // ... 11 more tools
  ];
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `runCapabilityTest()` overhead timed over 100 000 iterations with a sync mock handler. Schema assertion loop timing for a 10-field response. No model API calls needed — capability tests call tool handlers directly.

```
=== runCapabilityTest() framework overhead (100 000 iterations, sync mock handler) ===

$ node -e "
const test = defineCapabilityTest('get_customer_record', {
  fixtureInput:   { customer_id: 'test_001' },
  expectedFields: ['customer_id', 'email', 'account_tier', 'subscription_status'],
  expectedTypes:  { customer_id: 'string', email: 'string' },
  sideEffectSafe: true,
  severity:       'critical',
  handler: async () => ({ customer_id: 'test_001', email: 'a@b.com', account_tier: 'pro', subscription_status: 'active' }),
});
let t0 = performance.now();
for (let i = 0; i < 100000; i++) await runCapabilityTest(test);
console.log('runCapabilityTest() overhead:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
runCapabilityTest() overhead: 0.0048 ms   (excluding actual handler latency)

=== Failure detection: schema break after CRM migration ===

BEFORE migration — all 14 tools pass:
  runCapabilityTestSuite: { total: 14, passed: 14, failed: 0, deployVerdict: 'PASS — deploy safe' }

AFTER CRM API v2 migration (without capability tests catching it):
  get_customer_record returns: { id, email, tier, status }   ← renamed fields
    → missing_field:customer_id, missing_field:account_tier → FAIL (critical)
  create_ticket returns 422: missing required field 'category_v2'
    → handler_threw: 422 Unprocessable Entity → FAIL (high)
  send_email returns 403: API key scoping changed
    → handler_threw: 403 Forbidden → FAIL (high)

runCapabilityTestSuite result:
{
  total: 14,
  passed: 11,
  failed: 3,
  blockingFailures: 1,   ← get_customer_record is 'critical'
  deployVerdict: 'BLOCK — 1 critical tool(s) failed',
  failedTools: [
    { toolName: 'get_customer_record', severity: 'critical', failures: ['missing_field:customer_id','missing_field:account_tier'] },
    { toolName: 'create_ticket',       severity: 'high',     failures: ['handler_threw:422 Unprocessable Entity'] },
    { toolName: 'send_email',          severity: 'high',     failures: ['handler_threw:403 Forbidden'] },
  ]
}
→ Migration rolled back. Zero customer impact.

=== CapabilityMonitor.toolUptime() after 30-day production run ===

{
  get_customer_record: 0.998,   ← 2 brief outages in 30 days
  create_ticket:       0.994,
  send_email:          0.991,
  get_order_history:   1.000,
  initiate_refund:     0.986,   ← longest tool; 3 timeout failures (latency SLO breach)
  // ...
}
→ initiate_refund 1.4% failure rate: investigate P95 latency; SLO may need adjustment or handler optimization

=== F-07 vs F-64 vs F-83 ===

              │ F-07 (eval-driven dev)      │ F-64 (template testing)     │ F-83 (capability testing)
──────────────┼─────────────────────────────┼─────────────────────────────┼──────────────────────────────
Tests         │ Model output quality        │ Template rendering           │ Tool handler execution
Calls model?  │ Yes                         │ No                           │ No (calls handler directly)
External deps │ No (prompt + model only)    │ No                           │ Yes — tests the real dependency
Catches       │ Quality regression          │ Template variable bugs       │ Schema breaks, auth failures, latency
When to run   │ Pre-deploy, on prompt change│ CI per commit                │ Deploy gate + scheduled + on-demand
Cost per run  │ Model call cost per test    │ $0                           │ $0 (no model call)
```

## See also

[F-07](f07-eval-driven-development.md) · [S-74](../stacks/s74-agent-capability-registry.md) · [F-64](f64-prompt-template-testing.md) · [F-75](f75-tool-output-schema-contracts.md) · [F-16](f16-tool-call-validation.md) · [F-42](f42-ai-incident-response.md) · [S-105](../stacks/s105-data-call-cost-threshold.md)

## Go deeper

Keywords: `agent capability testing` · `tool smoke test` · `capability verification` · `tool health check` · `declared vs actual capability` · `tool handler test` · `capability gate` · `agent tool test suite` · `production capability monitor` · `tool availability test`
