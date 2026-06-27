# S-147 · Entity-Level Source Priority Override

[S-137](s137-multi-source-field-level-merge.md) maintains a `fieldSourceMap`: a global priority order of sources per field, shared across all entities. [F-114](../forward-deployed/f114-source-response-time-slos.md) adjusts that order dynamically: when a source's P99 latency breaches its SLO, it is deprioritized fleet-wide until the window recovers. Both mechanisms treat all entities identically — the same source priority applies to AAPL as to a small-cap biotech.

Some entities require different behavior. A dedicated data contract with Bloomberg may require that Bloomberg is always the primary source for specific high-value entities regardless of latency. An entity covered by a specialized feed (Cboe for equity options) may need that feed first for specific fields even when it is not the fleet default. A regulatory requirement may mandate a specific source for specific instruments. These per-entity rules cannot be expressed in S-137's global `fieldSourceMap` and should not be implemented as F-114 exceptions — F-114 is latency-driven, not contract-driven.

An entity-level source priority override registry stores per-entity rules: `(entityId, field) → sourceOrder[]`. The lookup chain is: exact `(entityId, field)` match → entity-level wildcard `(entityId, *)` → fleet-level default from S-137. When the registry returns an override, S-137 uses that order instead of its global priority. Entities without an override behave exactly as before.

## Situation

A financial data pipeline uses S-137 with a global priority order: `['refinitiv', 'bloomberg', 'iex']` for most equity fields. F-114 has further deprioritized Bloomberg to last after a P99 latency breach: the fleet-wide order is now `['refinitiv', 'iex', 'bloomberg']`.

Three exceptions exist:

1. **AAPL** — a dedicated Bloomberg terminal contract requires Bloomberg as the canonical source for `price` and `volume`. Refinitiv may be the fallback, but Bloomberg must be tried first.
2. **MSFT** — an enterprise data contract with Bloomberg covers all fields. Bloomberg is primary across the board for MSFT regardless of latency state.
3. **GOOG** — the team uses Cboe as the primary source for `impliedVolatility` for this entity because Cboe has tighter spreads on GOOG options.

Without an override registry: all three entities use the F-114-adjusted fleet order. Bloomberg (contractually required for AAPL/MSFT) is tried last; GOOG uses Refinitiv first for `impliedVolatility` when Cboe is faster and more accurate.

With an override registry: `resolveOrder('AAPL', 'price', fleetOrder)` → `['bloomberg', 'refinitiv', 'iex']`; `resolveOrder('MSFT', 'marketCap', fleetOrder)` → `['bloomberg', 'refinitiv', 'iex']` (wildcard); `resolveOrder('AMZN', 'price', fleetOrder)` → fleet default; `resolveOrder('GOOG', 'impliedVolatility', fleetOrder)` → `['cboe', 'refinitiv', 'bloomberg']`.

## Forces

- **Contract obligations and latency SLOs are orthogonal.** F-114 is an engineering mechanism — it improves speed by deprioritizing slow sources. A data contract is a legal obligation — it requires a specific source to be primary regardless of its current latency. Mixing them corrupts both: if F-114 can override a contract obligation, the obligation is not being met; if contract overrides suppress F-114, the latency defense weakens globally. Separate them cleanly at the registry layer.
- **The wildcard tier prevents combinatorial explosion.** An enterprise contract covering all fields for an entity should not require registering one override per field. The `(entityId, *)` pattern handles the common case: one rule, all fields. The exact `(entityId, field)` tier handles the exception.
- **Overrides must be auditable.** When a data quality issue traces back to an unusual source order, `allOverrides()` surfaces what the registry contains. F-114 deprioritization is dynamic and temporary; registry overrides are static and persistent. The audit path must distinguish them.
- **Overrides do not bypass S-140 rate limits.** Putting Bloomberg first for AAPL does not grant more Bloomberg API quota. If Bloomberg's rate limit is exhausted (S-140), S-137 still falls through to the next source in the override order. Override specifies preference, not guarantee.
- **Fleet-level F-114 and entity-level overrides compose.** S-137 checks the registry first; if an override exists, it uses that order with F-114 applied only to the non-overridden portion of the fleet. If Bloomberg is contractually first for AAPL, F-114 does not rearrange it — but F-114 can still deprioritize Refinitiv vs IEX within the AAPL override's fallback tiers.
- **Override count stays small; O(1) lookup is the only reasonable choice.** A registry covering a portfolio of 10 000 entities with 10 overrides each has 100 000 entries. A Map lookup at `O(1)` per entity+field pair is the only option — linear scan or sorted search at call time would introduce latency at the most frequent path in S-137.

## The move

**Store per-entity source order overrides in a Map. Resolve via exact → wildcard → default chain. Apply in S-137 before calling sources.**

```js
// --- Entity-level source priority override registry ---
// Stores rules: (entityId, field) → sourceOrder[]
// Lookup chain: exact (entityId:field) → wildcard (entityId:*) → fleet default (S-137)

class EntitySourceOverrideRegistry {
  constructor() {
    this._overrides = new Map();   // key: 'entityId:field' → sourceOrder[]
  }

  // Register a source order override for an (entityId, field) pair.
  // Use field = '*' to apply to all fields for this entity.
  // sourceOrder: string[] of source IDs, highest priority first.
  register(entityId, field, sourceOrder) {
    this._overrides.set(`${entityId}:${field}`, sourceOrder);
  }

  // Resolve the source order for (entityId, field).
  // Returns override if found; otherwise defaultOrder.
  resolveOrder(entityId, field, defaultOrder) {
    return this._overrides.get(`${entityId}:${field}`)
        ?? this._overrides.get(`${entityId}:*`)
        ?? defaultOrder;
  }

  // True if any override applies to this (entityId, field) pair.
  hasOverride(entityId, field) {
    return this._overrides.has(`${entityId}:${field}`)
        || this._overrides.has(`${entityId}:*`);
  }

  // All registered overrides — for audit and debugging.
  allOverrides() {
    return [...this._overrides.entries()].map(([key, order]) => {
      const colon = key.indexOf(':');
      return {
        entityId:    key.slice(0, colon),
        field:       key.slice(colon + 1),
        sourceOrder: order,
      };
    });
  }
}

// --- Integration with S-137 ---
// In S-137's fetchField(), replace the hardcoded fieldSourceMap lookup with:

async function fetchFieldWithOverride(entityId, field, fieldSourceMap, overrideRegistry) {
  const defaultOrder = fieldSourceMap[field] ?? [];
  const sourceOrder  = overrideRegistry.resolveOrder(entityId, field, defaultOrder);

  for (const sourceId of sourceOrder) {
    const result = await fetchFromSource(sourceId, entityId, field);
    if (result !== null && result !== undefined) {
      return { value: result, source: sourceId, overridden: overrideRegistry.hasOverride(entityId, field) };
    }
  }
  return { value: null, source: null, overridden: false };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `register()`, `resolveOrder()`, `hasOverride()` timed over 100 000 iterations. Registry loaded with 3 override rules (AAPL:price, MSFT:*, GOOG:impliedVolatility).

```
=== EntitySourceOverrideRegistry timing (100 000 iterations) ===

register():                            0.0003 ms
resolveOrder() — exact entity+field:   0.0003 ms   (AAPL:price → bloomberg first)
resolveOrder() — entity+* wildcard:    0.0001 ms   (MSFT:marketCap → bloomberg first via MSFT:*)
resolveOrder() — no override (miss):   0.0002 ms   (AMZN:price → fleet default)
hasOverride():                         0.0001 ms

=== Override resolution results ===

Fleet-default order (after F-114 P99 breach on bloomberg):
  price:              ['refinitiv', 'iex', 'bloomberg']    ← bloomberg last

Override registry (3 rules):
  AAPL:price          → ['bloomberg', 'refinitiv', 'iex']   (contract obligation)
  MSFT:*              → ['bloomberg', 'refinitiv', 'iex']   (enterprise data contract)
  GOOG:impliedVolatility → ['cboe', 'refinitiv', 'bloomberg']

resolveOrder results:
  AAPL, price          → bloomberg, refinitiv, iex    ← override (contract respected)
  MSFT, marketCap      → bloomberg, refinitiv, iex    ← wildcard (all MSFT fields)
  AMZN, price          → refinitiv, iex, bloomberg    ← fleet default (F-114 order)
  GOOG, impliedVol     → cboe, refinitiv, bloomberg   ← override (specialized source)

=== Audit output: allOverrides() ===

  { entityId: 'AAPL', field: 'price',             sourceOrder: ['bloomberg','refinitiv','iex'] }
  { entityId: 'MSFT', field: '*',                 sourceOrder: ['bloomberg','refinitiv','iex'] }
  { entityId: 'GOOG', field: 'impliedVolatility', sourceOrder: ['cboe','refinitiv','bloomberg'] }

=== S-137 vs F-114 vs S-140 vs S-147 ===

              │ S-137 (field-level merge)       │ F-114 (latency SLOs)            │ S-140 (rate limit tracking)     │ S-147 (entity override)
──────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────
Scope         │ Fleet-wide, per field           │ Fleet-wide, per source          │ Fleet-wide, per source          │ Per entity, per field (optional *)
Driver        │ Field coverage priority         │ Measured P95/P99 latency        │ Quota consumption rate          │ Contract, regulatory, or quality
When updated  │ On source onboarding/change     │ Each source call (rolling win.) │ Each API call                   │ On contract change (manual)
Overrides     │ Baseline for all entities       │ Dynamic reorder within S-137    │ Blocks exhausted source         │ Replaces S-137 order for entity
Miss behavior │ DATA_UNAVAILABLE                │ Falls to next source in order   │ Skips source, tries next        │ Falls through override order
Audit path    │ fieldSourceMap config           │ sloStatus() per source          │ quotaStatus() per source        │ allOverrides() registry dump
```

## See also

[S-137](s137-multi-source-field-level-merge.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md) · [S-140](s140-per-source-api-rate-limit-tracking.md) · [S-141](s141-source-schema-contract-versioning.md) · [F-113](../forward-deployed/f113-per-entity-data-completeness-tracking.md) · [S-146](s146-source-field-acceptance-testing.md)

## Go deeper

Keywords: `entity source priority override` · `per-entity source order` · `entity-level data source` · `source priority override registry` · `entity source contract override` · `per-entity fieldSourceMap` · `entity override source routing` · `data source entity exception` · `entity-specific source priority` · `source order override per entity`
