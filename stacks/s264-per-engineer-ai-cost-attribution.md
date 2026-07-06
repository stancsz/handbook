# S-264 · Per-Engineer AI Cost Attribution

Your CFO just asked why the engineering org burned through 40% of the annual AI budget in Q1. You pull the provider invoice — it shows total spend by model and date, nothing more. You can't answer the question. This is the gap: raw invoices don't map to engineers, teams, or products. Until you close that gap, every AI cost decision is a guess.

## Forces

- **Uber burned through its full-year AI coding budget in four months** (2026) after deploying Claude Code to ~5,000 engineers. Per-engineer costs ranged $500–$2,000/month. No one could see who was driving the bill until it was already blown. — [Bloomberg, The Information, May 2026](https://www.outlookbusiness.com/corporate/uber-caps-ai-tool-usage-after-exhausting-yearly-budget-in-just-4-months)
- **Microsoft revoked Claude Code licenses for ~100,000 engineers** in June 2026, citing external billing costs, and redirected them to GitHub Copilot — a product decision driven by attribution blindness.
- **Anthropic launched Enterprise Analytics API** (May 2026): per-user cost, usage, and engagement data across every Claude surface (chat, Code, Cowork, Office agents). Nine endpoints. Dollar amounts. Per named user. — [Finout](https://www.finout.io/blog/anthropic-enterprise-analytics)
- **Only 22% of organizations can attribute AI cost to a transaction.** 43% can attribute to a customer. Nearly zero can attribute to the engineer who triggered the call. — [CloudZero State of AI Costs, May 2025](https://cloudzero.com)
- **Per-seat AI tooling is collapsing the cost visibility stack.** GitHub Copilot, Claude Code, Cursor, Azure AI seats — each generates LLM calls your organization pays for, with no native hook into who triggered them.
- **AI spend is now an engineering KPI, not a finance curiosity.** The unit cost is decided in architecture and code. Without attribution, you cannot coach, optimize, or allocate it.

## The move

Per-engineer AI cost attribution traces every model call back to the human who initiated it — enabling chargeback, coaching, anomaly detection, and budget negotiation at the organizational layer.

### The three-level attribution chain

```
Provider Invoice
  └─ Account / API Key
      └─ Team / Department (tag via gateway header)
          └─ Engineer / User ID (tag via session or tool)
              └─ Feature / Workflow (tag via request metadata)
```

Each level requires instrumentation at a different boundary:

**Level 1 — Gateway tagging.** Every LLM gateway request carries a `X-User-ID` and `X-Team-ID` header injected from your auth layer before it reaches the provider. This is the single highest-leverage intervention — it works even when you don't control the client tool (Claude Code, Copilot, etc.).

**Level 2 — Client-side injection.** For tools you control (custom agents, IDE plugins, CI pipelines), embed user context in the request metadata or system prompt. LangChain, LlamaIndex, and most LLM gateway proxies support metadata fields for this.

**Level 3 — Provider-native APIs.** Anthropic Enterprise Analytics API (2026), OpenAI usage dashboards, and Azure AI Analytics export per-user breakdowns where available. Treat these as the ground-truth reconciliation source, not the primary attribution mechanism.

### The attribution schema

Tag every LLM call with four fields at minimum:

| Field | Source | Example |
|---|---|---|
| `engineer_id` | Auth token / session | `eng_7f3a92` |
| `team` | HRIS / SSO group | `platform-infra` |
| `tool` | Client library | `claude-code` / `cursor` / `copilot` |
| `feature` | Workflow / product | `code-review` / `doc-summarize` |

### Chargeback, not just visibility

Raw attribution data is a dashboard. Chargeback is the mechanism that changes behavior. Two models:

- **Soft cap:** Engineer sees their spend in the dashboard. Budget alerts fire at 80% of team allocation. No hard block — works for coaching and norm-setting.
- **Hard budget:** Engineering manager sets a monthly token/dollar ceiling per engineer or team. LLM gateway rejects or queues requests above the cap. Necessary when AI tooling is billing against a shared organizational budget.

### Anomaly detection on the attribution feed

Once you have per-engineer attribution, simple rules catch runaway patterns:

- Engineer exceeds 3× team median spend in a single week
- Single session generates >$500 in LLM calls (catch the overnight loop)
- Unusual tool-to-cost ratio (e.g., a code-review tool burning 10× more than historical baseline)

### Reconciliation

Attribution logs are not the invoice. Reconcile against provider usage data monthly:

```python
# Reconcile attribution log against provider invoice
provider_usage = anthropic_client.analytics.export(date_range="2026-05")
attribution_log = query_cost_logs_by_team(team="platform-infra")

# Check for untagged calls — indicates gateway or client instrumentation gap
untagged = provider_usage.total_calls - sum(t.attributed_calls for t in attribution_log)
assert untagged / provider_usage.total_calls < 0.02, f"{untagged} untagged calls ({untagged/provider_usage.total_calls:.1%})"
```

> 2% untagged tolerance accounts for internal health checks and infrastructure calls.

## Receipt

> Receipt pending — June 30, 2026. The pattern is grounded in real incidents (Uber 2026, Microsoft/Claude Code 2026) and Anthropic's May 2026 Enterprise Analytics API launch. The attribution schema and reconciliation code reflect standard LLM gateway instrumentation patterns. Hard validation requires a live gateway with tagged requests against an actual provider invoice.

## See also

- [S-208 · Per-Tenant LLM Cost Attribution](stacks/s208-per-tenant-llm-cost-attribution.md) — customer-level attribution, not engineer-level
- [S-243 · Agentic Inference Cost Stratification](stacks/s243-agentic-inference-cost-stratification.md) — why agentic loops explode cost
- [S-211 · Agent Token Budget Guardrails](stacks/s211-agent-token-budget-guardrails.md) — enforcing cost ceilings at the agent level
- [F-88 · Session Cost Ceiling](forward-deployed/f88-session-cost-ceiling.md) — dollar-denominated abort for open-ended agent loops
- [F-08 · Agent Cost Control](forward-deployed/f08-agent-cost-control.md) — operational cost discipline
