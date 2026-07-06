# S-210 · Agentic Knowledge Compilation

Traditional RAG fetches documents at query time. Agentic knowledge compilation does the fetching, structuring, and indexing at build or deploy time — so runtime is a lookup, not a retrieval. The result: sub-100ms retrieval latency, elimination of the retrieval-quality → answer-quality cascade, and agents grounded on deterministic, auditable artifacts rather than probabilistic retrieval.

## Forces

- 73% of enterprise RAG deployments fail in or before production — not because of bad models, but because of retrieval infrastructure decisions made in the first weeks of development
- Query-time retrieval is the dominant latency bottleneck in agentic pipelines — embedding + vector search + re-ranking adds 200–800ms per query that no model upgrade fixes
- The "retrieval confidence → answer quality" cascade is invisible and non-linear — a 0.85 retrieval score doesn't mean an 85% answer quality
- Static knowledge bases (policies, schemas, FAQs, product catalogs) change infrequently — re-retrieving them per query is pure waste
- RAG failure is misdiagnosed as a model problem 80% of the time — teams tune prompts, swap embeddings, and expand context windows while the structural problem compounds
- Agent context windows are finite and expensive — feeding the agent 40 retrieved chunks on every turn burns tokens on information it already had

## The move

The pattern has three layers: **compile**, **index**, **lookup**.

### 1. Compile: extract structured knowledge at build time

Run a domain-specific extraction pass over your knowledge corpus. Produce typed, structured artifacts — not raw chunks.

```python
# compile.py — run at build/deploy time
import json
from pathlib import Path

def compile_knowledge(kb_dir: Path, output: Path):
    artifacts = []

    for doc in kb_dir.glob("**/*.md"):
        sections = extract_sections(doc.read_text())
        for section in sections:
            # Extract structured key-value and list facts
            facts = extract_structured_facts(section)
            for fact in facts:
                artifacts.append({
                    "type": fact.type,       # "policy" | "schema" | "faq" | "rule"
                    "subject": fact.subject,   # "refund" | "user" | "order"
                    "predicate": fact.predicate,  # "max_days" | "required_fields"
                    "value": fact.value,
                    "source": str(doc),
                    "chunk_id": fact.chunk_id,
                })

    # Write deterministic, versioned artifact
    output.write_text(json.dumps({
        "version": "1.0",
        "compiled_at": str(Path("/proc/self/fd/1").resolve()),
        "artifacts": artifacts,
    }, indent=2))

def extract_structured_facts(section: str) -> list[Fact]:
    # Use an LLM call here — one-time cost, not per-query
    prompt = f"""
Extract structured facts from this section as JSON:
{{"facts": [{{"type": "...", "subject": "...", "predicate": "...", "value": "..."}}]}}

Section:
{section}
"""
    return parse_llm_json(prompt).facts
```

### 2. Index: build a lightweight lookup index

Build a two-level index over the compiled artifacts. Level 1: a fast keyword/trie index for exact-match queries. Level 2: a semantic index only for ambiguous or multi-hop queries.

```python
# index.py
from collections import defaultdict

class KnowledgeIndex:
    def __init__(self, artifacts: list[dict]):
        # Level 1: keyword index — O(1) lookup for exact queries
        self.keyword_idx: dict[str, list[dict]] = defaultdict(list)
        # Level 2: semantic index — only if keyword lookup returns >5 results
        self.semantic_idx: list[dict] = artifacts
        self.artifacts = artifacts

    def lookup(self, query: str, mode: str = "auto") -> list[dict]:
        # Fast path: exact keyword match
        keywords = extract_keywords(query)
        candidates = []
        for kw in keywords:
            candidates.extend(self.keyword_idx.get(kw, []))

        if len(candidates) >= 3 and mode == "auto":
            # Deterministic, sub-10ms
            return deduplicate(candidates)
        elif len(candidates) < 3:
            # Fall back to semantic — accept the latency
            return semantic_search(query, self.semantic_idx, top_k=5)
        else:
            return candidates[:5]
```

### 3. Lookup: replace retrieval with index access at runtime

```python
# agent.py
class CompiledKnowledgeAgent:
    def __init__(self, index_path: Path):
        self.index = KnowledgeIndex.load(index_path)

    def think(self, user_query: str) -> str:
        # Sub-100ms — no embedding, no vector search, no re-ranking
        facts = self.index.lookup(user_query)

        if not facts:
            # Graceful fallback — not a silent failure
            return self.fallback_retrieval(user_query)

        grounded_context = format_facts(facts)
        return self.llm.generate(
            system="Answer from the grounded context. If insufficient, say so explicitly.",
            user=user_query,
            context=grounded_context,
        )
```

### When to compile vs. retrieve

| Knowledge type | Change frequency | Pattern |
|---|---|---|
| Product schema, API specs | Rare | Compile |
| Legal/policy documents | Rare | Compile |
| FAQs, runbooks | Medium | Compile + refresh on deploy |
| Real-time inventory, prices | Continuous | RAG (query-time) |
| User-specific data | Continuous | Direct DB query |
| News, social feeds | Continuous | RAG (query-time) |

**Compile everything that changes less than once per week.** The refresh-on-deploy trigger is: a CI job that recompiles when the knowledge base changes and bumps the artifact version.

## Receipt

> Receipt pending — June 30, 2026

The pattern is documented in production at multiple teams (Anthropic customer references, Knolli blog). The implementation above is minimal-functional — a real production version would add artifact versioning, diff-based invalidation (only recompile changed docs), and TTL-based fallback to RAG for stale artifacts.

## See also

- [S-07 · RAG](s07-rag.md) — Traditional retrieval pattern; compile is the build-time complement
- [S-207 · Semantic Caching for Agents](s207-semantic-caching-for-agents.md) — Caches at the query-result level; compile works at the knowledge level
- [S-206 · Context Debt](s206-context-debt.md) — Compile directly reduces context debt by pre-filtering what the agent sees
