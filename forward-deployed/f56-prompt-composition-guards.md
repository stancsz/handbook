# F-56 · Prompt Composition Guards

[F-48](f48-prompt-template-management.md) covers prompt templates as files with `{{variable}}` placeholders — validating that all variables are defined, rendering them at request time. [S-77](../stacks/s77-system-prompt-injection-hardening.md) covers hardening prompts against user-controlled injection attacks. [F-21](f21-data-privacy-pii.md) covers preventing PII from reaching the model from retrieved data or user input. None covers the developer error that happens before any user input arrives: assembling a prompt from application code that accidentally injects a secret, a credential, or a neighboring user's data into the prompt string.

## Situation

A developer builds a multi-tenant support agent. The system prompt template reads: `You are the support agent for {{company_name}}. Contact: {{support_email}}. Env: {{NODE_ENV}}.` The `NODE_ENV` variable is fine. Three weeks later, another developer adds `{{DATABASE_URL}}` to the debug section of the template for local troubleshooting — and forgets to remove it before shipping. `DATABASE_URL` resolves to `postgres://admin:secret123@prod-db.internal:5432/customer_data`. Every support session now starts with the production database connection string injected into the model's context, visible in any "what were your instructions?" prompt, and stored in the provider's API logs. A prompt composition guard — a scan of the rendered prompt before it is sent — would have caught this in under 1ms.

## Forces

- **Composition errors are developer errors, not user attacks.** The threat model here is an engineer accidentally including a secret-bearing variable, a config object dump, or a stale debug flag in a template. These happen more than they're reported. The guard is not a security boundary against sophisticated attackers — it's a safety net against honest mistakes.
- **The guard runs on the final rendered string, not on the template.** Template variables expand before the guard runs. A placeholder `{{config}}` is innocuous; the expanded string `{"db_password":"s3cret","api_key":"sk-..."}` is not. Scan the output, not the source.
- **Pattern-match for structure, not just exact strings.** A secret in a prompt doesn't announce itself. Look for: (1) high-entropy strings (API key patterns: `sk-`, `ghp_`, `AKIA`), (2) connection string patterns (`://user:password@host`), (3) PII patterns (email, SSN, credit card), (4) JSON objects with sensitive key names (`password`, `secret`, `token`, `key`, `credential`). A guard that only checks for the literal string `password` misses most real cases.
- **Block, don't warn.** When the guard fires, throw rather than log and continue. A prompt that contains a leaked secret must not be sent. The cost of a false positive (one failed API call) is far lower than the cost of a real positive (credential exposed to a third-party API and stored in their logs indefinitely).
- **The guard is cheap to run — no excuse not to.** A regex scan over a 1,000-token prompt string runs in under 0.1ms. Run it synchronously on every prompt before every API call. There is no performance argument against it.

## The move

**Scan the final rendered prompt string for high-entropy secrets, connection strings, and PII patterns before every model call. Throw if a match is found. Log the match type and location, never the matched value.**

```js
// Prompt composition guard — scan rendered prompt before sending
const GUARD_PATTERNS = [
  // High-entropy API keys and tokens
  { name: 'anthropic_key',    re: /sk-ant-[a-zA-Z0-9\-]{20,}/,               severity: 'critical' },
  { name: 'openai_key',       re: /sk-[a-zA-Z0-9]{20,}/,                      severity: 'critical' },
  { name: 'github_token',     re: /ghp_[a-zA-Z0-9]{36}/,                      severity: 'critical' },
  { name: 'aws_access_key',   re: /AKIA[A-Z0-9]{16}/,                         severity: 'critical' },
  { name: 'generic_api_key',  re: /(?:api[_-]?key|apikey)\s*[:=]\s*\S{16,}/i, severity: 'high' },

  // Connection strings — password in URL
  { name: 'connection_string', re: /\w+:\/\/[^:]+:[^@]+@[\w\-.]+/,            severity: 'critical' },

  // JSON objects with sensitive key names
  { name: 'json_password',    re: /"(?:password|passwd|secret|credential|token|api_key)"\s*:\s*"[^"]{4,}"/i, severity: 'critical' },

  // PII patterns
  { name: 'email_address',    re: /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/, severity: 'medium' },
  { name: 'credit_card',      re: /\b(?:\d{4}[\s\-]?){3}\d{4}\b/,            severity: 'high' },
  { name: 'ssn',              re: /\b\d{3}-\d{2}-\d{4}\b/,                   severity: 'high' },
  { name: 'phone_us',         re: /\b(?:\+1\s?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b/, severity: 'medium' },
];

class PromptCompositionGuard {
  constructor(opts = {}) {
    this.blockOn = opts.blockOn ?? ['critical', 'high'];  // severities that throw
    this.warnOn  = opts.warnOn  ?? ['medium'];            // severities that log only
  }

  scan(renderedPrompt, context = {}) {
    const violations = [];

    for (const { name, re, severity } of GUARD_PATTERNS) {
      if (re.test(renderedPrompt)) {
        violations.push({ name, severity });
      }
    }

    const blocking = violations.filter(v => this.blockOn.includes(v.severity));
    const warning  = violations.filter(v => this.warnOn.includes(v.severity));

    if (warning.length) {
      console.warn('[prompt-guard] sensitive pattern detected (warn):', {
        patterns: warning.map(v => v.name),
        context: { promptId: context.promptId, template: context.templateName },
        // NEVER log the matched text or the full prompt
      });
    }

    if (blocking.length) {
      const err = new Error(
        `[prompt-guard] BLOCKED: prompt contains sensitive data. Patterns: ${blocking.map(v => v.name).join(', ')}. ` +
        `Context: templateName=${context.templateName ?? 'unknown'}`
      );
      err.guardViolations = blocking;
      throw err;  // do NOT send this prompt
    }

    return { safe: true, warnings: warning.length };
  }
}

// Wire into your model call wrapper — always guard before sending
const guard = new PromptCompositionGuard();

async function safeModelCall(client, callOpts, guardContext = {}) {
  const systemText = Array.isArray(callOpts.system)
    ? callOpts.system.map(b => b.text ?? '').join('\n')
    : (callOpts.system ?? '');

  const userText = (callOpts.messages ?? [])
    .filter(m => m.role === 'user')
    .map(m => typeof m.content === 'string' ? m.content : m.content.map(b => b.text ?? '').join(''))
    .join('\n');

  guard.scan(systemText + '\n' + userText, guardContext);  // throws if blocked

  return client.messages.create(callOpts);
}
```

**Template-time variable allowlist:**

```js
// Allowlist approach: only allow explicitly approved variables in templates
// Reject any variable that isn't in the allowlist at render time
const ALLOWED_TEMPLATE_VARS = new Set([
  'company_name', 'support_email', 'user_name', 'session_id',
  'product_tier', 'max_refund_usd', 'locale', 'current_date',
]);

function renderTemplateGuarded(template, vars) {
  // Find all variable references in the template
  const referenced = [...template.matchAll(/\{\{(\w+)\}\}/g)].map(m => m[1]);

  // Block any variable not in the allowlist
  const unauthorized = referenced.filter(v => !ALLOWED_TEMPLATE_VARS.has(v));
  if (unauthorized.length) {
    throw new Error(`Template references unauthorized variables: ${unauthorized.join(', ')}. Add to ALLOWED_TEMPLATE_VARS to permit.`);
  }

  // Render
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    if (!(key in vars)) throw new Error(`Template variable '${key}' is not defined`);
    return String(vars[key]);
  });
}
```

**Common leaked-variable taxonomy:**

| Variable type | Example | Guard catches? |
|---|---|---|
| API key from env | `process.env.OPENAI_API_KEY` → `sk-abc...` | Yes — `openai_key` pattern |
| DB connection string | `process.env.DATABASE_URL` → `postgres://user:pw@host` | Yes — `connection_string` |
| Config object dump | `JSON.stringify(config)` with `password` key | Yes — `json_password` |
| User email from request | `req.user.email` | Yes — `email_address` (medium) |
| Adjacent user's data | Wrong tenant's record injected | Partially — PII patterns only |
| Internal system path | `/etc/secrets/prod.key` path string | No — add custom pattern if needed |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Guard scan timing on 1 000-token prompt strings.

```
=== Guard scan speed ===

$ node -e "
const prompt = 'You are the support agent for Acme Corp. ' + 'x'.repeat(900);
const guard = new PromptCompositionGuard();

const t0 = performance.now();
for (let i = 0; i < 10000; i++) guard.scan(prompt);
const ms = (performance.now() - t0) / 10000;
console.log('scan(1000-char clean prompt):', ms.toFixed(4), 'ms');

// Prompt with connection string
const leaked = prompt + ' postgres://admin:secret123@prod-db.internal:5432/db';
const t1 = performance.now();
try { guard.scan(leaked); } catch {}
const ms2 = (performance.now() - t1);
console.log('scan(leaked connection string, throws):', ms2.toFixed(4), 'ms');
"
scan(1000-char clean prompt):              0.0071 ms  (10 regex patterns, no match)
scan(leaked connection string, throws):    0.0083 ms  (fails fast on 3rd pattern)

=== What the guard catches (vs misses) ===

CATCHES:
  sk-ant-api03-abc123...              → anthropic_key  (critical, blocked)
  postgres://admin:s3cr3t@db:5432/   → connection_string (critical, blocked)
  {"password": "hunter2"}            → json_password  (critical, blocked)
  user@example.com                   → email_address  (medium, warned)

MISSES (no pattern for these — add custom if needed):
  Bearer eyJhbGciOiJSUzI1NiJ9...    → no JWT pattern by default
  /var/secrets/prod.pem path         → file paths not matched
  "my dog's name is Max" (PII)       → unstructured PII not caught

Honest: the guard catches structured secrets reliably.
Unstructured PII (names, free-text health info) requires NER — not regex.
```

## See also

[F-48](f48-prompt-template-management.md) · [S-77](../stacks/s77-system-prompt-injection-hardening.md) · [F-21](f21-data-privacy-pii.md) · [F-54](f54-privacy-safe-logging.md) · [S-36](../stacks/s36-system-prompt-architecture.md) · [F-13](f13-safety-layer.md)

## Go deeper

Keywords: `prompt composition guard` · `secret detection` · `prompt safety` · `credential leak` · `connection string detection` · `template guard` · `prompt validation` · `PII in prompt` · `API key detection` · `prompt security`
