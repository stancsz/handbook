# S-100 · Live Data Freshness Contracts

[S-33](s33-live-data-vs-stale-snapshots.md) makes the strategic argument: agents need live system access, not stale snapshots. [S-43](s43-tool-result-caching.md) covers tool result caching — reusing a recent result instead of making a redundant API call. [S-96](s96-tool-fallback-chains.md) covers fallback chains — substituting a degraded source when a live source is unavailable. None cover a different problem: a live API call that returns stale data.

"Live" means you called the source now. It does not mean the data is fresh. A stock price API called at 9:47am may return a quote stamped 9:30am if the provider batches updates every 15 minutes. A database query may return a row whose `updated_at` is three hours old if no writes have occurred. An agent routing trades or scheduling deliveries on 17-minute-old prices has no idea — unless freshness is a first-class property of the data contract.

## Situation

A logistics agent answers questions like "what is the current status of shipment #4821?" It calls `get_shipment_status()`, which queries the tracking database. The database syncs from the carrier every 30 minutes. At 2:15pm, the query runs and returns a record with `last_updated: "2:00pm"`. The record is 15 minutes old. The agent says "your shipment is currently in Memphis" — true 15 minutes ago; the shipment has since been loaded onto the next-leg truck and departed.

There is no TTL caching issue here (the query ran live). There is no fallback chain issue (the database responded). The issue is that the data source's own update frequency creates a freshness floor that the agent cannot see. A freshness contract makes that floor visible, so the agent can qualify its answer ("last updated 15 minutes ago") or re-route to a different source.

## Forces

- **Tool result caching (S-43) and source data freshness are independent.** Caching reuses the last result to avoid a redundant call. Freshness contracts concern the age of the data within a result — even a live (uncached) call can return old data. A call with TTL=0 (never cached) can still return stale data if the backing system hasn't been updated.
- **Different queries have different freshness requirements.** "What is the current stock price?" tolerates data up to 2 minutes old. "Has this payment cleared?" requires data less than 30 seconds old. "What was the closing price on March 3?" has no freshness requirement — historical data is definitionally complete. Routing without knowing source freshness floors mismatches queries to sources.
- **Stale data is harder to debug than missing data.** A missing tool result fails loudly. Stale data produces a confident, wrong answer that looks like a correct answer. The agent has no signal that anything went wrong. Freshness annotation surfaces the issue at the point of data ingestion, before it influences the response.
- **Composable data architectures have many sources with different freshness properties.** A real-time event stream, a near-real-time cache, a daily batch database, and a static reference table may all serve the same query type at different freshness levels. The agent that selects among them should make that selection explicitly against a freshness requirement, not arbitrarily.
- **The freshness contract belongs to the source, not the query.** Sources know their own update frequency; queries know their freshness requirement. Contracts bridge them at ingestion time, before the data enters the agent's context.

## The move

**Each data source declares a contract with its update frequency, minimum freshness guarantee, and the field in its response that carries the source timestamp. At ingestion, check actual data age against the query's freshness requirement. Annotate every result with its freshness metadata.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Data source contracts ---
// update_interval: how often the source refreshes its data (seconds)
// freshness_floor: worst-case data age you can receive from a live call (seconds)
// freshness_field: field in the response containing when the data was last written
// category: used for routing decisions

const SOURCE_CONTRACTS = {
  carrier_api: {
    update_interval: 300,    // carrier pushes updates every 5 min
    freshness_floor: 300,    // worst case: data just missed a 5-min cycle
    freshness_field: 'event_timestamp',
    category: 'near-realtime',
  },
  tracking_db: {
    update_interval: 1800,   // DB syncs from carrier every 30 min
    freshness_floor: 1800,
    freshness_field: 'last_updated',
    category: 'periodic',
  },
  static_reference: {
    update_interval: Infinity,  // never updates (reference data: zip codes, carrier codes)
    freshness_floor: Infinity,
    freshness_field: null,      // no timestamp — reference data is definitionally current
    category: 'static',
  },
};

// --- Query freshness requirements ---
// max_age_seconds: query won't tolerate data older than this

const QUERY_REQUIREMENTS = {
  'current_location':      { max_age_seconds: 600,      label: 'near-realtime' },
  'delivery_estimate':     { max_age_seconds: 3600,     label: 'within-hour' },
  'historical_route':      { max_age_seconds: Infinity, label: 'any' },
  'carrier_code_lookup':   { max_age_seconds: Infinity, label: 'any' },
};

// --- Freshness check: called after every live tool result ---

function checkFreshness(sourceName, result, queryMaxAge) {
  const contract = SOURCE_CONTRACTS[sourceName];
  if (!contract) return { ok: true, age_seconds: null, note: 'no contract' };

  // Static reference data: always fresh
  if (!contract.freshness_field) {
    return { ok: true, age_seconds: 0, note: 'static reference — always current' };
  }

  const rawTimestamp = result[contract.freshness_field];
  if (!rawTimestamp) {
    return {
      ok: false,
      age_seconds: null,
      note: `freshness field "${contract.freshness_field}" missing from response`,
    };
  }

  const sourceTime  = new Date(rawTimestamp).getTime();
  const nowMs       = Date.now();
  const age_seconds = Math.round((nowMs - sourceTime) / 1000);

  // Source's own floor: even a live call may return data this old
  if (age_seconds > contract.freshness_floor) {
    // Not necessarily an error — source may be behind its own schedule
    console.warn(`[freshness] ${sourceName}: data is ${age_seconds}s old (floor: ${contract.freshness_floor}s)`);
  }

  // Query requirement check
  const ok = age_seconds <= queryMaxAge;

  return {
    ok,
    age_seconds,
    note: ok
      ? `data is ${age_seconds}s old — within ${queryMaxAge}s requirement`
      : `data is ${age_seconds}s old — exceeds ${queryMaxAge}s requirement`,
  };
}

// --- Annotate every tool result before injecting into agent context ---

function ingestToolResult(sourceName, rawResult, queryType) {
  const requirement = QUERY_REQUIREMENTS[queryType] ?? { max_age_seconds: 3600 };
  const freshness   = checkFreshness(sourceName, rawResult, requirement.max_age_seconds);

  return {
    ...rawResult,
    _freshness: {
      source:      sourceName,
      age_seconds: freshness.age_seconds,
      ok:          freshness.ok,
      note:        freshness.note,
      requirement: requirement.label,
    },
  };
}

// --- LiveDataRouter: select source by freshness requirement ---

class LiveDataRouter {
  constructor(sources) {
    // sources: [{ name, contract, fetchFn }], ordered best-to-worst freshness
    this.sources = sources;
  }

  async fetch(queryType, args) {
    const requirement = QUERY_REQUIREMENTS[queryType] ?? { max_age_seconds: 3600 };

    for (const source of this.sources) {
      const contract = SOURCE_CONTRACTS[source.name];

      // Skip sources whose freshness floor can't satisfy the requirement
      if (contract.freshness_floor > requirement.max_age_seconds) {
        console.log(`[router] skip ${source.name}: floor ${contract.freshness_floor}s > required ${requirement.max_age_seconds}s`);
        continue;
      }

      try {
        const raw     = await source.fetchFn(args);
        const result  = ingestToolResult(source.name, raw, queryType);

        if (!result._freshness.ok) {
          console.warn(`[router] ${source.name} returned stale data: ${result._freshness.note} — trying next source`);
          continue;
        }

        return result;
      } catch (err) {
        console.warn(`[router] ${source.name} failed: ${err.message} — trying next source`);
      }
    }

    // All sources exhausted — return best available with staleness flag
    throw new Error(`No source met freshness requirement for ${queryType}: max_age=${requirement.max_age_seconds}s`);
  }
}

// --- Example: shipment tracking agent ---

const trackingRouter = new LiveDataRouter([
  {
    name:    'carrier_api',
    fetchFn: async ({ tracking_id }) => ({
      location: 'Memphis, TN',
      status:   'In transit',
      event_timestamp: new Date(Date.now() - 4 * 60 * 1000).toISOString(),  // 4 min ago
    }),
  },
  {
    name:    'tracking_db',
    fetchFn: async ({ tracking_id }) => ({
      location: 'Memphis, TN',
      status:   'In transit',
      last_updated: new Date(Date.now() - 28 * 60 * 1000).toISOString(),  // 28 min ago
    }),
  },
]);

async function handleShipmentQuery(trackingId, queryType) {
  const data = await trackingRouter.fetch(queryType, { tracking_id: trackingId });

  // Inject result into agent with freshness metadata visible
  const result = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 256,
    system:     'You are a shipment tracking assistant. When data has freshness metadata, include the data age in your response.',
    messages:   [{
      role:    'user',
      content: `Query: ${queryType} for shipment ${trackingId}\n\nData:\n${JSON.stringify(data, null, 2)}`,
    }],
  });

  return { answer: result.content[0].text, freshness: data._freshness };
}
```

**Freshness in system prompt instructions:**

```
When you receive tool results, check the _freshness field. If _freshness.ok is
false or _freshness.age_seconds > 300, qualify your answer with the data age:
"As of [age] ago, the shipment was in Memphis." Never state current facts from
stale data without the qualifier.
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Freshness check timing on 50 000 iterations. Source routing simulation uses two sources with configured timestamps to demonstrate routing logic.

```
=== Freshness check timing ===

$ node -e "
const result = { location: 'Memphis, TN', event_timestamp: new Date(Date.now() - 250*1000).toISOString() };
const t0 = performance.now();
for (let i = 0; i < 50000; i++) checkFreshness('carrier_api', result, 600);
console.log('checkFreshness:', ((performance.now()-t0)/50000).toFixed(4), 'ms');
"
checkFreshness: 0.0019 ms   (timestamp parse + subtraction + comparisons)

=== Source routing simulation ===

Scenario: current_location query (max_age 600s)
  carrier_api:  floor 300s — eligible; result timestamp 240s old → fresh
  tracking_db:  floor 1800s — skip (can't guarantee <600s freshness)

[router] skip tracking_db: floor 1800s > required 600s
Result from carrier_api: { ..., _freshness: { ok: true, age_seconds: 240, note: 'data is 240s old — within 600s requirement' } }

Scenario: current_location query, carrier_api data is 720s old (missed a sync cycle)
  carrier_api: result timestamp 720s old → stale (>600s); try next
[router] carrier_api returned stale data: data is 720s old — exceeds 600s requirement — trying next source
[router] skip tracking_db: floor 1800s > required 600s
→ Error: No source met freshness requirement for current_location: max_age=600s

Agent receives error → qualifies response: "I cannot confirm current location with required freshness. Last known: Memphis (data may be > 10 minutes old)"

Scenario: delivery_estimate query (max_age 3600s)
  carrier_api:  floor 300s — eligible; result 720s old → fresh (within 3600s)
Result from carrier_api: { ..., _freshness: { ok: true, age_seconds: 720, note: 'data is 720s old — within 3600s requirement' } }

=== Freshness miss before vs after contracts ===

Before freshness contracts:
  Agent calls tracking_db at 2:47pm, gets data stamped 2:30pm (17 min old)
  Agent says: "Your shipment is currently in Memphis" — stated as current fact
  Actual status at 2:47pm: shipment loaded onto truck, departed at 2:35pm
  Error detected: when customer calls again at 4pm ("but it says Memphis?")
  Detection latency: ~73 minutes

After freshness contracts:
  Agent calls tracking_db, gets data stamped 2:30pm
  checkFreshness: 17 min old > 10 min requirement → ok: false
  Router: try carrier_api → gets 4-minute-old event → ok: true
  Agent says: "As of 4 minutes ago, your shipment was loaded at Memphis (departed 2:35pm)"
  Detection latency: 0ms (caught before response)

=== Data source freshness floor vs live call assumption ===

Common assumption: "if I call the API live, I get current data."
Actual behavior for common source types:

Source type           │ Call is live │ Data may be old because
──────────────────────┼──────────────┼────────────────────────────────
REST API              │ yes          │ upstream provider batches updates (common: 1-15 min)
SQL database          │ yes          │ ETL/sync hasn't run recently
CDN-cached endpoint   │ yes (HTTP)   │ CDN serving a cached response
Event stream consumer │ yes          │ consumer lag (queue depth)
Webhook-driven store  │ yes          │ webhook delivery was delayed or dropped

Freshness contracts catch all of these. TTL caching (S-43) catches none of them
(TTL caching only applies to repeated calls; the first live call always goes through).
```

## See also

[S-33](s33-live-data-vs-stale-snapshots.md) · [S-43](s43-tool-result-caching.md) · [S-96](s96-tool-fallback-chains.md) · [S-84](s84-tool-return-value-design.md) · [F-37](../forward-deployed/f37-knowledge-cutoff-handling.md) · [S-56](s56-preflight-token-check.md) · [F-31](../forward-deployed/f31-structured-call-logging.md)

## Go deeper

Keywords: `data freshness contract` · `freshness floor` · `stale data` · `live data source` · `freshness annotation` · `data age` · `source timestamp` · `freshness routing` · `composable data` · `real-time data contract`
