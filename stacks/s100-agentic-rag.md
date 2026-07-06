# S-100 · Agentic RAG

[S-07](s07-rag.md) covers the basic RAG loop: embed query → vector search → inject chunks → generate. It works for simple document Q&A. It breaks when the corpus is large, heterogeneous, or requires multi-hop reasoning — when "find the relevant chunk" itself is a non-trivial decision.

Agentic RAG replaces the static retrieval pipeline with an agent that *plans* retrieval, *revises* its approach based on results, and *chains* multiple reasoning steps before answering.

## Forces

- **Naive RAG hits a ceiling at ~1 million chunks.** Top-K retrieval finds good chunks for obvious queries but silently fails for complex, multi-concept, or ambiguous ones.
- **Retrieval quality varies by query type.** A query rewritten for a database engineer ("what is the schema for user_events") needs different retrieval than a natural-language question ("how many users churned after the last billing outage?").
- **Static RAG cannot self-correct.** If the first retrieval pass fails to find useful chunks, the system returns a hallucinated answer rather than retrying.
- **Knowledge graphs unlock relational reasoning.** "Which department's Q3 revenue was affected by the vendor outage in August?" requires traversing relationships, not finding chunks.

## The move

Agentic RAG adds four capabilities on top of basic RAG:

**1. Query rewriting.** Before retrieval, the agent reformulates the user query into 1–3 retrieval-optimized variants. "What happened to the platform during peak traffic?" → ["platform performance during peak load", "system outage peak traffic", "capacity issues high traffic incidents"].

**2. Multi-hop retrieval.** Instead of one-shot top-K, the agent retrieves → reads → formulates a sub-question → retrieves again → synthesizes. Chain 2–4 hops depending on query complexity.

**3. Knowledge graph (GraphRAG).** For structured corporate data, build an entity-relationship graph from documents. Query the graph first for relational context, then retrieve document chunks anchored to graph nodes.

**4. Self-correction / retreival critique.** After generating an answer, the agent checks: "Do the retrieved chunks actually support this claim?" If confidence is low, it re-retrieves with different keywords or a broader scope.

```python
from openai import OpenAI
from your_vector_db import VectorDB
from your_graph_db import GraphDB

client = OpenAI()
vector_db = VectorDB()
graph_db = GraphDB()

def agentic_rag(query: str, top_k: int = 5) -> str:
    # Step 1: Rewrite query into retrieval variants
    rewrite_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "system",
            "content": "Rewrite this query into 2-3 different retrieval-optimized phrasings. "
                       "Return as a JSON array of strings."
        }, {
            "role": "user",
            "content": query
        }],
        response_format={"type": "json_object"}
    )
    query_variants = list(eval(rewrite_response.choices[0].message.content).values())[0]

    # Step 2: Parallel vector search across all variants
    all_chunks = []
    for variant in query_variants:
        chunks = vector_db.search(variant, top_k=top_k)
        all_chunks.extend(chunks)
    # Deduplicate by chunk ID
    seen, unique_chunks = set(), []
    for c in all_chunks:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique_chunks.append(c)

    # Step 3: Graph retrieval for relational context
    graph_context = graph_db.query(
        f"MATCH (e1)-[r]-(e2) WHERE e1.name CONTAINS $query "
        "RETURN e1, r, e2 LIMIT 20",
        {"query": query}
    )

    # Step 4: Agent decides: synthesize now, or retrieve more?
    context_chunks = "\n\n".join([c["text"] for c in unique_chunks[:10]])
    graph_text = "\n".join([
        f"{g['e1']} --[{g['r']}]--> {g['e2']}"
        for g in graph_context
    ])

    planning_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "system",
            "content": "Given the retrieved context and graph data, decide: "
                       "can you answer the user query fully, or do you need another retrieval pass? "
                       "Respond with JSON: {\"ready\": bool, \"sub_question\": string | null}"
        }, {
            "role": "user",
            "content": f"Query: {query}\n\nChunks:\n{context_chunks}\n\nGraph:\n{graph_text}"
        }],
        response_format={"type": "json_object"}
    )
    decision = eval(planning_response.choices[0].message.content)

    # Step 5: If not ready, do a second retrieval pass with sub-question
    if not decision["ready"]:
        extra_chunks = vector_db.search(decision["sub_question"], top_k=5)
        context_chunks += "\n\n" + "\n\n".join([c["text"] for c in extra_chunks])

    # Step 6: Final synthesis
    final_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "system",
            "content": "Answer the user's question using ONLY the provided context. "
                       "If the context doesn't contain enough information, say so explicitly. "
                       "Cite specific chunks when making claims."
        }, {
            "role": "user",
            "content": f"Query: {query}\n\nContext:\n{context_chunks}"
        }]
    )
    return final_response.choices[0].message.content
```

**When to use each layer:**

| Query type | Pattern |
|---|---|
| Single-hop factual ("what is X?") | Basic RAG (S-07) |
| Multi-concept / ambiguous | Query rewriting |
| Relational ("affected by", "caused by", "before/after") | GraphRAG |
| Complex multi-step ("how did X impact Y through Z?") | Multi-hop + critique |
| Everything in production above 100K chunks | Agentic RAG |

**Tradeoffs:**
- Latency: each extra hop adds 200–800ms. Budget 3–5x over basic RAG.
- Cost: 2–4 LLM calls per query instead of 1. Worth it when accuracy matters.
- Complexity: the agent loop is harder to debug than a fixed pipeline. Add tracing (see [S-235](s235-production-failure-to-regression-test.md)).

## Receipt

> Receipt pending — 2026-07-01

## See also

- [S-07 · RAG](s07-rag.md) — foundational retrieval loop
- [S-82 · Semantic Query Routing](s82-semantic-query-routing.md) — routing to specialized agents by domain
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — when to decompose into sub-agents
