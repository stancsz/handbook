# S-48 · Memory Write Routing

Not all facts belong in the same place. A piece of information that arrives in the agent's turn needs to be routed to the right memory tier — or discarded. The routing decision determines what gets remembered, how fast it's retrieved, and how much it costs every subsequent call.

## Situation

A support agent receives an uploaded meeting-notes file (420 tokens) and a user preference ("metric units"). The agent injects both into context for the session. Ten turns later, both are still in context costing $1.26/k calls for the meeting notes alone — even though the agent has stopped referencing them. The meeting notes should have been written to the vector store (cost: $0.000008/write); the preference to the KV store (cost: ~$0/write). Both would be retrieved when needed and absent when not.

## Forces

- Context is the most expensive storage tier, not the most capable one. Keeping a 420-token document in context costs $1.26 per 1,000 calls — more than the entire embedding cost ($0.000008). The break-even between vector-store write and carrying in context is 1 call. After that, the vector store is cheaper for every call.
- Different fact types have different recall patterns. A structured fact (user name, account ID) is recalled by exact key. An episodic event (what happened last Tuesday) is recalled by semantic similarity. Forcing episodic facts into a KV store requires knowing the key at retrieval time — which you often don't. Forcing structured facts into a vector store adds embedding overhead and fuzzy matching where exact matching is available and correct.
- Procedural memory (learned workflows, tool sequences) should live in the system prompt or as a skill ([S-20](s20-agent-skills.md)), not in a retrieval store. It is used on every call and deserves the cacheable prefix slot ([S-08](s08-prompt-caching.md)).
- Working memory (current-turn scratchpad) should not be persisted at all. A partial plan, a draft calculation, an intermediate tool result — these are turn-local and the cost of persisting them exceeds the value.
- TTL is part of the write decision, not an afterthought. A preference fact needs a long TTL; a session task state needs to expire at session end; an episodic event should be evicted by recency score when the store grows beyond a threshold.

## The move

**Route each incoming fact to the cheapest tier that supports its recall pattern.**

| Fact type | Route to | TTL | Recall pattern | Why not context |
|---|---|---|---|---|
| Current-turn scratchpad | In-context (discard at turn end) | 1 turn | — | Ephemeral; never persist |
| Session task state | In-context + KV ([S-38](s38-agent-state-design.md)) | Session | Exact key | Fast cross-turn; structured |
| Structured user facts | KV store | Weeks–months | Exact key lookup | No embedding needed |
| Episodic events | Vector store | Long; evict by recency | Semantic similarity | Fuzzy recall; not key-lookup |
| Large documents / knowledge | Vector store (chunked) | Until deleted | Semantic query | Too large for context |
| Learned workflows | System prompt / skill ([S-20](s20-agent-skills.md)) | Permanent | Always-on | Reused every call; cacheable |

**Write routing logic (applied when a new fact arrives):**

```js
function routeFact(fact) {
  if (fact.scope === 'current_turn')  return 'discard_at_turn_end';
  if (fact.scope === 'session')       return 'kv_store';    // + keep in context while active
  if (fact.type === 'structured')     return 'kv_store';    // key-value lookup
  if (fact.type === 'episodic')       return 'vector_store';
  if (fact.tokens > 100)              return 'vector_store'; // chunked
  if (fact.type === 'procedural')     return 'system_prompt_update';
  return 'kv_store';                                         // default: structured
}
```

**Retrieval pre-load vs just-in-time.** For structured facts the agent will likely need (user name, active plan), pre-load from KV at session start. For episodic and document facts, retrieve just-in-time via query — only inject what the current turn needs. The S-09 dual-tier pattern (hot = in-context + KV; cold = vector) is the production form of this.

**Eviction policy is a write-time decision.** When writing to the vector store, set: (a) a TTL if the fact has a natural expiry; (b) a relevance score field for scoring-based eviction when the store exceeds size limits. Treat memory stores the same as any database — they need schema, TTL, and cleanup.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Cost model from real token measurements. Embedding price: $0.02/M tokens (typical 2026 embedding model). Input price: $3.00/M tokens.

```
=== Memory write cost comparison: five fact types ===

Fact                                  in-ctx cost/1k-calls   embed+store cost
User name (5 tokens)                     $0.015/k              $0.00010/write
Preference (8 tokens)                    $0.024/k              $0.00016/write
Structured record (12 tokens)            $0.036/k              $0.00024/write
Support ticket (180 tokens)              $0.540/k              $0.00360/write
Meeting notes (420 tokens)              $1.260/k              $0.00840/write

=== Break-even: vector store vs in-context carry ===
Meeting notes (420 tokens):
  Embed-and-store cost:  $0.000008
  In-context cost/call:  $0.00126/call
  Break-even:            1 call — after that, vector is always cheaper
```

The break-even is 1 call for a 420-token document. Embedding is so cheap relative to input token pricing that any document larger than a few words should be stored and retrieved rather than injected and carried. The only reason to keep facts in context is when retrieval latency is unacceptable for the current turn — not as a default.

## See also

[S-09](s09-memory-systems.md) · [S-38](s38-agent-state-design.md) · [S-07](s07-rag.md) · [S-08](s08-prompt-caching.md) · [S-20](s20-agent-skills.md)

## Go deeper

Keywords: `memory routing` · `agent memory` · `write routing` · `vector store` · `KV store` · `in-context memory` · `episodic memory` · `memory TTL` · `eviction policy` · `Mem0` · `Zep`
