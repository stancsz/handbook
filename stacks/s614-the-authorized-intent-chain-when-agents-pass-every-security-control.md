# S-614 · The Authorized Intent Chain

When Tenet Security (June 2026) validated an attack against real organizations — injecting crafted markdown into Sentry error events, having AI coding agents read and act on those events, and exfiltrating Git credentials, environment variables, and private repository URLs — they described it as the **Authorized Intent Chain**: every individual action was technically permitted, logged, and auditable. No malware was dropped. No policy was violated. No anomaly was flagged. EDR, WAF, IAM, VPN, Cloudflare, and firewalls were all bypassed — not by defeating them, but by never triggering them. The same properties that make agents productive (broad tool access, standing credentials, autonomous action on what they read) are the exact properties an attacker borrows.

## Forces

- **Every security control enforces authorization, not intent.** IAM checks whether a principal can call an API. WAF checks for known attack signatures. EDR checks for malicious binaries. None of them ask: *was this action consistent with the human's actual goal?* An agent acting on injected content is making authorized API calls with legitimate credentials.
- **Agents operationalize arbitrary text as instructions.** Unlike human operators who are bounded by intent and habit, an agent that reads "run this diagnostic command" in an error event will run it — even when the event was planted by an attacker. The agent has no concept of trusted vs. untrusted data sources.
- **Credential standing multiplies blast radius.** Agent credentials are designed to persist — they grant ongoing access, not session-scoped access. A compromised agent credential gives an attacker persistent, legitimate access across every system the agent can reach.
- **Injection + autonomous execution = production-grade exploit chain.** Prompt injection alone is a data problem. Add an agent with tool access and the ability to run on schedule, and you have persistent code execution with no social engineering, no phishing, and no malware detection surface.

## The move

The Authorized Intent Chain is not a single vulnerability — it is a structural property of how agentic systems interact with the existing security perimeter. The fix is architectural, not a new scanner.

**1. Treat agent-accessible data sources as untrusted inputs.**
The agent's context window is an attack surface. Sentry events, retrieved documents, email content, Slack messages, and database fields that the agent reads from are all injection vectors. Tag every data source by trust level and sanitize or scope data accordingly.

**2. Bind credentials to the specific task scope, not the agent identity.**
Agents with broad credentials (read: all production agents) need scoped, short-lived tokens that limit lateral movement. An agent that can only write to the systems it needs for its current task cannot exfiltrate Git credentials when it gets compromised.

**3. Require provenance on every action the agent takes.**
The immutable audit ledger pattern (S-604) is necessary but not sufficient: it proves *what* the agent did, not *what signal triggered it*. Tag each tool call with the source of the instruction that caused it. If the agent emails a client, log whether that instruction came from the user's message, a document it retrieved, or an error event it read.

**4. Separate signal sources from instruction sources.**
Not all text an agent processes is meant as instruction. Sentry error events are diagnostic data. Pull request comments are communication. Only a named, explicit instruction channel should be treated as directives. Build this distinction into the agent's system prompt and tool design — not as a heuristic, but as a structural property.

**5. Collapse the MCP trust chain for agent-accessible integrations.**
The agentjacking attack worked because Sentry's MCP server returned unvalidated event data as if it were trusted system output. Every MCP server in an agent's integration chain is a potential injection point. Audit every MCP connection for whether it accepts arbitrary external input (it, email, error tracking, webhooks) and apply the same sanitization you'd apply to user messages.

```
[Attacker]  →  [Sentry DSN / error event]  →  [Agent reads event as data]
                                              ↓
                                        [Agent infers instruction]
                                              ↓
                                    [Tool call: run diagnostic script]
                                              ↓
                              [Exfil: git creds, env vars, tokens]
                                              ↓
                              [Attacker: receives exfil on port 443]

  Security controls: EDR ✗ | WAF ✗ | IAM ✗ | VPN ✗ | Firewall ✗
  Why it passes: every step uses authorized credentials + legitimate tools
```

## Receipt

> Verified 2026-07-05 — Agentjacking attack documented by Tenet Security (Ron Bobrov et al.), June 12 2026. 2,388 organizations identified with exposed and injectable Sentry DSNs; 71 in Tranco top 1M. Controlled validation across 100+ organizations with Claude Code, Cursor, and Codex showed 85% exploitation success rate. Sentry acknowledged the architectural flaw is "technically not defensible" and activated a content filter for specific payload strings. No existing security control (EDR, WAF, IAM, VPN, Cloudflare, firewall) detects or blocks the attack because no individual action violates policy.

## See also

- [S-599 · The Reasoning-Execution Boundary](s599-the-reasoning-execution-boundary.md) — structural separation as the strongest prompt injection defense
- [S-602 · The MCP Trust Surface Is Unbounded Until You Sandbox It](s602-the-mcp-trust-surface-is-unbounded-until-you-sandbox-it.md) — MCP auto-discovery collapses trust boundaries
- [S-604 · The Immutable Audit Ledger](s604-the-immutable-audit-ledger.md) — audit trail that captures provenance, not just actions
- [S-375 · Agentic Prompt Injection: Defense-in-Depth for Production](s375-agentic-prompt-injection-defense-in-depth-for-production.md) — layered injection defense
