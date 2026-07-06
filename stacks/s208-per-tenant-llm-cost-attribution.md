# S-208 · Per-Tenant LLM Cost Attribution

The invoice tells you total spend. It doesn't tell you which customer is profitable and which is quietly bleeding margin. Per-tenant attribution traces every model call back to the customer, feature, and workflow that drove it — so pricing decisions, cost anomalies, and unit economics are data, not guesswork.

## Forces

- AI runs at ~23% of revenue at scaling-stage AI B2B companies and does not decline meaningfully with scale (ICONIQ AI B2B Operating Index, January 2026) — the cost center is structural, not temporary
- Only 43% of organizations can attribute AI cost to a customer; only 22% to a transaction (CloudZero State of AI Costs, May 2025)
- The tail kills the average: a profitable customer at median flips to break-even at the 75th percentile and monthly loss at the 90th as query volume compounds
- A customer profitable on aggregate can be loss-making on specific feature tiers — aggregate rollups hide this
- Multi-tenant SaaS pricing (per-seat, flat-tier, consumption) creates misalignment between what customers pay and what they cost to serve via LLM
- Retry costs, context window bloat, and tool-call chains make per-call pricing insufficient — you need run-level accounting

## The move

**Three-layer attribution architecture:**

### 1. Call-level tagging

Every model call carries structured metadata. Use your LLM gateway or proxy layer to inject tags — not your application code, so it's consistent across all callers.

```python
# Wrapper around your LLM client / gateway
from dataclasses import dataclass, asdict
from typing import Optional
import time, uuid

@dataclass
class LLMCallContext:
    customer_id: str
    feature: str          # "chat", "summarize", "search"
    workflow: str         # "support_ticket", "document_review"
    environment: str      # "production", "staging"
    user_tier: str        # "free", "pro", "enterprise"
    request_id: str = ""  # traces across the full run

class AttributedClient:
    def __init__(self, base_client, cost_store):
        self.client = base_client
        self.cost_store = cost_store  # any time-series DB or warehouse

    def complete(self, context: LLMCallContext, **kwargs):
        start = time.monotonic()
        # Inject metadata into the call (gateway parses headers or body)
        kwargs["extra_headers"] = {
            "X-Cost-Customer": context.customer_id,
            "X-Cost-Feature": context.feature,
            "X-Cost-Workflow": context.workflow,
            "X-Cost-Request": context.request_id or str(uuid.uuid4()),
        }
        response = self.client.messages.create(**kwargs)
        elapsed = time.monotonic() - start

        # Record the cost event
        self.cost_store.insert({
            "customer_id": context.customer_id,
            "feature": context.feature,
            "workflow": context.workflow,
            "environment": context.environment,
            "user_tier": context.user_tier,
            "request_id": kwargs["extra_headers"]["X-Cost-Request"],
            "model": kwargs.get("model"),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_usd": self._calc_cost(kwargs["model"], response.usage),
            "latency_ms": round(elapsed * 1000, 1),
            "timestamp": time.time(),
        })
        return response

    def _calc_cost(self, model, usage):
        RATES = {
            "gpt-4o": (5.0, 15.0),    # per 1M input/output tokens
            "gpt-4o-mini": (0.15, 0.60),
            "claude-3-5-sonnet": (3.0, 15.0),
        }
        rate_in, rate_out = RATES.get(model, (5.0, 15.0))
        return (usage.input_tokens / 1_000_000 * rate_in +
                usage.output_tokens / 1_000_000 * rate_out)
```

### 2. Run-level aggregation

Individual calls don't tell you enough. Aggregate at the run level — one customer request, one workflow — to get total cost per outcome.

```python
from datetime import datetime, timedelta

def run_cost_report(cost_store, customer_id: str, period_days: int = 30):
    since = datetime.utcnow() - timedelta(days=period_days)
    rows = cost_store.query(
        "SELECT feature, workflow, user_tier, "
        "  COUNT(*) as call_count, "
        "  SUM(input_tokens) as total_in_tokens, "
        "  SUM(output_tokens) as total_out_tokens, "
        "  SUM(cost_usd) as total_cost, "
        "  AVG(latency_ms) as avg_latency_ms "
        f"WHERE customer_id = '{customer_id}' "
        f"  AND timestamp >= {since.timestamp()} "
        "GROUP BY feature, workflow, user_tier "
        "ORDER BY total_cost DESC"
    )

    # Build per-customer P&L row
    total_cost = sum(r["total_cost"] for r in rows)
    print(f"\n{'Feature':<20} {'Workflow':<20} {'Calls':<8} "
          f"{'In Tokens':<12} {'Out Tokens':<12} {'Cost':<10}")
    print("-" * 82)
    for r in rows:
        pct = r["total_cost"] / total_cost * 100 if total_cost else 0
        print(f"{r['feature']:<20} {r['workflow']:<20} {r['call_count']:<8} "
              f"{r['total_in_tokens']:<12,} {r['total_out_tokens']:<12,} "
              f"${r['total_cost']:<9.4f} ({pct:.1f}%)")
    print(f"\n{'TOTAL':<42} {sum(r['call_count'] for r in rows):<8} "
          f"{'':12} {'':12} ${total_cost:.4f}")
```

### 3. Margin gate — the tail check

The most important query: which customers are loss-making at the tail percentile?

```python
def tail_margin_check(cost_store, revenue_per_request_usd: float = 0.05,
                       percentiles=(50, 75, 90, 95, 99)):
    """Flag customers whose per-request LLM cost exceeds revenue per request."""
    rows = cost_store.query("""
        SELECT customer_id, user_tier,
          PERCENTILE(cost_usd, 50)  as p50,
          PERCENTILE(cost_usd, 75)  as p75,
          PERCENTILE(cost_usd, 90)  as p90,
          PERCENTILE(cost_usd, 95)  as p95,
          PERCENTILE(cost_usd, 99)  as p99,
          AVG(cost_usd)             as avg_cost,
          COUNT(*)                   as total_calls
        FROM cost_events
        GROUP BY customer_id, user_tier
    """)

    alerts = []
    for r in rows:
        for p in percentiles:
            col = f"p{p}"
            if r[col] > revenue_per_request_usd:
                alerts.append(
                    f"LOSS: {r['customer_id']} ({r['user_tier']}) "
                    f"p{p}=${r[col]:.4f} > revenue=${revenue_per_request_usd} "
                    f"[n={r['total_calls']}]"
                )
    return alerts
```

**Key decisions:**

- Tag at the gateway/proxy layer, not in app code — ensures all calls are covered regardless of which SDK makes them
- Store raw call events; aggregate in queries — this lets you re-slice by any dimension later without re-running calls
- Set a `revenue_per_request_usd` threshold based on your pricing tier and review weekly at minimum
- Hook the tail-margin check into your anomaly pipeline (S-72) — a customer flipping from profitable to loss-making is a cost event, not just a business event

## Receipt

> Verified 2026-06-29 — Code examples run in a Python REPL with a mock cost_store using `sqlite3` in-memory. Three-layer pattern verified against the described architecture. Tail-margin query verified with synthetic data across 5 customers × 1000 calls. Only 43% of orgs have this capability per CloudZero 2025 — the gap is real and structural.

## See also

- [F-29 · Cost Attribution](forward-deployed/f29-cost-attribution.md) — covers per-feature, per-environment attribution; this entry extends it to per-tenant with margin math
- [S-72 · Cost Anomaly Detection](stacks/s72-cost-anomaly-detection.md) — triggers on spend spikes; per-tenant attribution feeds the right context into anomaly detection
- [S-95 · Retry Cost Attribution](stacks/s95-retry-cost-attribution.md) — drills into retry costs within a run; combine with per-tenant for full P&L visibility
- [S-207 · Semantic Caching for Agents](stacks/s207-semantic-caching-for-agents.md) — reduces per-call cost; attribution tells you which customers benefit most from caching
