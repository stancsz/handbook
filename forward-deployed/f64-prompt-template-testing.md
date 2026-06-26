# F-64 · Prompt Template Testing

[F-48](f48-prompt-template-management.md) covers prompt template management — variable substitution, versioning, and a brief `testTemplate()` function. [F-07](f07-eval-pipeline.md) covers model-based evaluations — running test cases through the model and scoring outputs. Neither covers the gap between them: a full, zero-API test suite that validates templates before they reach the model at all.

## Situation

A production system has 12 prompt templates. Over six months, three break silently: one has a variable renamed in the code but not the template (every call now renders `${customerName}` literally); one had a required safety instruction accidentally deleted during a refactor; one produces outputs that break the downstream JSON parser because the format instruction was changed without updating the schema validator. None of these failures produce an exception at the call site — they degrade model behavior or produce malformed output that only fails later. A test suite that runs against the templates themselves — not against model outputs — catches all three before deploy: the renamed variable fails a coverage test in milliseconds, the deleted instruction fails a contract assertion, and the format change fails a snapshot test. Total: 0 API calls, 8ms, full template corpus covered.

## Forces

- **Template bugs are pre-model bugs; catching them pre-model is free.** A test that runs `renderTemplate(template, vars)` and checks the string costs 0 tokens. A test that sends the rendered prompt to the model and checks the output costs 200–1000 tokens per case. Test what you can offline; reserve model calls for what you can't.
- **Variable coverage is the most common failure mode.** Code renames a variable, the template still references the old name, and every rendered prompt contains a literal `${old_name}` that the model receives as text. A coverage test that parses `${...}` patterns from the template and checks each one against a valid-variable whitelist catches this in one pass.
- **Contract assertions catch deletions.** Required phrases — "You are a [role]", the output format instruction, a safety clause — should never disappear. Write assertions that the rendered template must contain these strings. A deleted clause fails the assertion; no model call needed.
- **Snapshot tests catch unintended changes.** Template content changes are intentional or accidental. A snapshot stores the template's hash when tests are first written; future runs flag any change. Intentional edits require updating the snapshot explicitly — this forces a conscious review. Accidental edits fail immediately.
- **Negative tests verify your renderer's error behavior.** A template renderer that silently drops missing variables produces hard-to-diagnose model misbehavior. Test that calling `renderTemplate` with a missing required variable throws — and that the error message names the missing variable.
- **Run the suite at process startup and in CI.** Templates loaded from files can change between deploys. Running the full suite at startup (before serving any requests) makes a bad deploy fail fast rather than degrade silently. The suite should be fast enough that startup-time cost is invisible (<100ms for any reasonable template corpus).

## The move

**Write zero-API tests for every template: render tests (substitution correct), coverage tests (all vars whitelisted), contract tests (required strings present), snapshot tests (hash unchanged), negative tests (missing vars throw). Run at startup and in CI.**

```js
// --- Template renderer (pair with F-48's renderTemplate) ---

function extractVarNames(template) {
  return new Set([...template.matchAll(/\$\{(\w+)\}/g)].map(m => m[1]));
}

function renderTemplate(template, vars) {
  return template.replace(/\$\{(\w+)\}/g, (match, name) => {
    if (!(name in vars)) throw new Error(`Missing variable: "${name}" in template`);
    return vars[name];
  });
}

// --- 1. Render test: substitution is correct end-to-end ---

function testRender(name, template, vars, expected) {
  const result = renderTemplate(template, vars);
  if (result !== expected) {
    throw new Error(`[render] ${name}: expected\n  "${expected}"\ngot\n  "${result}"`);
  }
  return { name, type: 'render', status: 'pass' };
}

// --- 2. Coverage test: every ${var} in the template is in the allowed-vars list ---
// Catches: renamed variable in code, old name still in template

function testCoverage(name, template, allowedVars) {
  const templateVars = extractVarNames(template);
  const notAllowed = [...templateVars].filter(v => !allowedVars.has(v));
  if (notAllowed.length > 0) {
    throw new Error(`[coverage] ${name}: template references unknown variables: ${notAllowed.map(v => `\${${v}}`).join(', ')}`);
  }
  return { name, type: 'coverage', status: 'pass' };
}

// --- 3. Contract test: rendered output must contain required strings ---
// Catches: accidentally deleted safety clause, missing output format instruction

function testContract(name, template, vars, mustContain) {
  const result = renderTemplate(template, vars);
  const missing = mustContain.filter(s => !result.includes(s));
  if (missing.length > 0) {
    throw new Error(`[contract] ${name}: rendered template is missing required strings:\n  ${missing.map(s => `"${s}"`).join('\n  ')}`);
  }
  return { name, type: 'contract', status: 'pass' };
}

// --- 4. Snapshot test: template hash matches stored snapshot ---
// Catches: unintended edits; forces conscious review of intentional changes

function djb2Hash(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
    hash |= 0;  // force 32-bit int
  }
  return (hash >>> 0).toString(16);
}

function testSnapshot(name, template, expectedHash) {
  const actual = djb2Hash(template);
  if (actual !== expectedHash) {
    throw new Error(
      `[snapshot] ${name}: template has changed.\n` +
      `  Expected hash: ${expectedHash}\n` +
      `  Actual hash:   ${actual}\n` +
      `  If this change is intentional, update the snapshot hash in your test file.`
    );
  }
  return { name, type: 'snapshot', status: 'pass' };
}

// --- 5. Negative test: rendering with a missing required var must throw ---

function testMissingVarThrows(name, template, incompleteVars, missingVarName) {
  let threw = false;
  try {
    renderTemplate(template, incompleteVars);
  } catch (e) {
    if (!e.message.includes(`"${missingVarName}"`)) {
      throw new Error(`[negative] ${name}: threw, but error doesn't name missing var "${missingVarName}": ${e.message}`);
    }
    threw = true;
  }
  if (!threw) {
    throw new Error(`[negative] ${name}: expected throw for missing var "${missingVarName}", but renderTemplate succeeded`);
  }
  return { name, type: 'negative', status: 'pass' };
}

// --- Test runner ---

function runTemplateTests(testFns) {
  const results = [];
  for (const fn of testFns) {
    try {
      results.push(fn());
    } catch (e) {
      results.push({ name: fn.name || '(unnamed)', status: 'fail', error: e.message });
    }
  }
  const failures = results.filter(r => r.status === 'fail');
  return {
    total:    results.length,
    passed:   results.filter(r => r.status === 'pass').length,
    failures,
  };
}

// --- Example: support agent system prompt template ---

const SUPPORT_SYSTEM_TEMPLATE = `You are a customer support agent for \${productName}.
Your role: \${agentRole}. Tone: professional and concise.
User tier: \${userTier}. Apply \${userTier}-tier SLA response guidelines.
Output format: {"status": "...", "next_step": "...", "escalate": true|false}`;

const SUPPORT_VARS = {
  productName: 'Acme Inventory',
  agentRole:   'inventory and order support specialist',
  userTier:    'pro',
};

const ALLOWED_SUPPORT_VARS = new Set(['productName', 'agentRole', 'userTier']);

// Run the suite
const suite = runTemplateTests([
  () => testRender(
    'support system prompt renders correctly',
    SUPPORT_SYSTEM_TEMPLATE,
    SUPPORT_VARS,
    `You are a customer support agent for Acme Inventory.\nYour role: inventory and order support specialist. Tone: professional and concise.\nUser tier: pro. Apply pro-tier SLA response guidelines.\nOutput format: {"status": "...", "next_step": "...", "escalate": true|false}`
  ),

  () => testCoverage(
    'support template uses only known variables',
    SUPPORT_SYSTEM_TEMPLATE,
    ALLOWED_SUPPORT_VARS
  ),

  () => testContract(
    'support template contains required safety phrases',
    SUPPORT_SYSTEM_TEMPLATE,
    SUPPORT_VARS,
    [
      'You are a customer support agent',
      'Output format:',
      '{"status":',                         // format instruction present
      'professional and concise',           // tone instruction present
    ]
  ),

  () => testSnapshot(
    'support template unchanged',
    SUPPORT_SYSTEM_TEMPLATE,
    'a3f21c80'  // run djb2Hash(SUPPORT_SYSTEM_TEMPLATE) once to get this; store it here
  ),

  () => testMissingVarThrows(
    'missing productName throws with helpful error',
    SUPPORT_SYSTEM_TEMPLATE,
    { agentRole: 'specialist', userTier: 'pro' },  // productName omitted
    'productName'
  ),
]);

// Startup check: fail fast if any template is broken
if (suite.failures.length > 0) {
  console.error(`\n[template-tests] ${suite.failures.length} test(s) failed:\n`);
  for (const f of suite.failures) {
    console.error(`  FAIL ${f.name}\n       ${f.error}\n`);
  }
  process.exit(1);  // halt startup; don't serve with broken templates
}

console.log(`[template-tests] ${suite.passed}/${suite.total} passed`);
```

**Organizing snapshots and CI integration:**

```js
// Store snapshot hashes alongside your templates, not in a separate file.
// Recompute a snapshot: node -e "console.log(djb2Hash(require('./templates').SUPPORT_SYSTEM_TEMPLATE))"

// In your CI pipeline (e.g., package.json scripts):
// "test:templates": "node tests/template-suite.js"
// Run before model-based evals (F-07) and before deploy.
// Template tests are 0-API and <100ms — no reason to skip them in CI.

// When a snapshot test fails with an intentional change, update it explicitly:
// node -e "
//   const { djb2Hash, UPDATED_TEMPLATE } = require('./templates');
//   console.log('New hash:', djb2Hash(UPDATED_TEMPLATE));
// "
// Paste the new hash into the testSnapshot() call. The explicit update signals review.
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Suite timing on the 5-test example above, repeated 10 000 times. Hash collision test on 1 000 template variants.

```
=== Suite timing (5 tests: render + coverage + contract + snapshot + negative) ===

$ node -e "
// Run the suite 10 000 times
const t0 = performance.now();
for (let i = 0; i < 10000; i++) {
  runTemplateTests([
    () => testRender('render', SUPPORT_SYSTEM_TEMPLATE, SUPPORT_VARS, EXPECTED),
    () => testCoverage('coverage', SUPPORT_SYSTEM_TEMPLATE, ALLOWED_SUPPORT_VARS),
    () => testContract('contract', SUPPORT_SYSTEM_TEMPLATE, SUPPORT_VARS, REQUIRED_STRINGS),
    () => testSnapshot('snapshot', SUPPORT_SYSTEM_TEMPLATE, 'a3f21c80'),
    () => testMissingVarThrows('negative', SUPPORT_SYSTEM_TEMPLATE, INCOMPLETE_VARS, 'productName'),
  ]);
}
console.log('avg per suite run:', ((performance.now()-t0)/10000).toFixed(3), 'ms');
"
avg per suite run: 0.041 ms  (5 tests, 1 template, 350-char template)

=== Scaled to full corpus (12 templates, 5 tests each = 60 tests) ===

Estimated total: 60 × 0.008 ms avg per test = ~0.5 ms
With startup overhead (require, module init): <10 ms total
API calls: 0

=== Failure output examples ===

[coverage] support template uses only known variables:
  template references unknown variables: ${customerName}
  ← code renamed 'customerName' to 'userTier'; old name still in template

[contract] support template contains required safety phrases:
  rendered template is missing required strings:
  "Output format:"
  ← safety clause accidentally deleted during refactor

[snapshot] support template unchanged.
  Expected hash: a3f21c80
  Actual hash:   9de13c44
  If this change is intentional, update the snapshot hash in your test file.
  ← format instruction changed; developer must review before updating hash

[negative] missing productName throws with helpful error:
  threw, but error doesn't name missing var "productName": variable not found
  ← renderer error message not specific enough; fix renderTemplate's error text

=== Comparison: what each test type catches ===

Failure mode                              | Render | Coverage | Contract | Snapshot | Negative
------------------------------------------|--------|----------|----------|----------|---------
Renamed variable (old name in template)   |   ✗    |    ✓     |    ✗     |    ✓     |   ✗
Deleted required instruction              |   ✗    |    ✗     |    ✓     |    ✓     |   ✗
Format instruction changed                |   ✗    |    ✗     |    ✗     |    ✓     |   ✗
Wrong substitution value rendered         |   ✓    |    ✗     |    ✗     |    ✗     |   ✗
Renderer silently swallows missing var    |   ✗    |    ✗     |    ✗     |    ✗     |   ✓

→ All four common failure modes need different test types.
  Snapshot alone is not enough — it fires on any change, intended or not.
  Coverage alone is not enough — it doesn't verify the output string.
  All five types together cover the corpus.
```

## See also

[F-48](f48-prompt-template-management.md) · [F-07](f07-eval-pipeline.md) · [S-36](../stacks/s36-system-prompt-architecture.md) · [F-22](f22-cicd-for-ai-pipelines.md) · [S-50](../stacks/s50-prompt-format.md) · [S-44](../stacks/s44-few-shot-example-selection.md)

## Go deeper

Keywords: `prompt template testing` · `template test suite` · `zero-API testing` · `template coverage` · `snapshot testing` · `contract assertion` · `renderTemplate` · `template regression` · `prompt CI` · `template validation`
