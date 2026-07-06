# S-378 · Entity Grounding — Knowledge Graphs as the Verifiable Memory Layer

Your agent answered a compliance question about Acme Corp's subsidiary structure. The answer was confident, sourced, and wrong — it conflated Acme Inc. (public parent) with Acme LLC (private subsidiary), two legally distinct entities with different regulatory obligations. The vector retrieval found chunks mentioning "Acme" in both contexts, and the model interpolated between them. This is not a generation hallucination. This is a retrieval hallucination — the agent retrieved semantically plausible chunks without understanding entity identity. Vector RAG cannot distinguish "Acme Inc." from "Acme LLC." A knowledge graph can.

## Forces

- **Vector RAG matches text, not entities.** Semantic similarity retrieves chunks about related topics, not the specific entity you asked about. As corpus size grows, the signal-to-noise ratio collapses — a "Acme" search in a 10M-chunk corpus surfaces hundreds of unrelated matches
- **Chunk boundaries destroy relationship context.** A knowledge graph encodes "Acme LLC is a subsidiary of Acme Inc. and is regulated by FINRA" as a first-class fact. The same fact, embedded in a 2,000-token document chunk, must be retrieved intact and then correctly extracted by the LLM — two failure points instead of zero
- **Enterprise knowledge is fundamentally relational.** Legal, financial, and compliance domains are entity-centric: subsidiaries, contracts, regulatory relationships, ownership chains. These are graphs, not documents
- **More capable models hallucinate more confidently.** A model that retrieves the wrong chunk generates a more believable wrong answer than one working from thin context. Grounding at the entity level, before generation, is the only structural fix
- **The accuracy ceiling for vector RAG on multi-hop reasoning is ~17%.** Microsoft's GraphRAG research demonstrated a 3.4× improvement (16.7% → 56.2%) by grounding the same LLM in a knowledge graph on multi-hop queries. This gap is architectural, not a model upgrade problem

## The move

**The pattern: replace document-chunk retrieval with entity-level graph traversal as the primary grounding layer.** The knowledge graph becomes the agent's long-term, verifiable memory — each fact has provenance, typed relationships, and is retrieved by entity resolution, not semantic similarity.

```
Query → Entity Extraction → Knowledge Graph Traverse → Provenance Chain → Generate + Cite
                ↑                                                        ↓
         (optional fallback)                              Verify answer entities against graph
         Vector RAG (for unstructured text)               before surfacing
```

**Key implementation decisions:**

**1. Graph schema as the domain model.**
Define entity types and relationship types before ingestion. Common enterprise types: `Person`, `Organization`, `Contract`, `Regulation`, `Product`, `Event`. Relationships carry directionality and properties: `subsidiary →`, `regulated_by →`, `party_to →`. The schema is the contract between your data and your agent's reasoning.

**2. Entity resolution is non-optional.**
Names alone are not unique identifiers. "Acme Corp" vs "Acme Corporation" vs "ACME INC." must resolve to the same canonical entity. Use deterministic normalization (uppercase, strip punctuation) as a minimum; probabilistic entity linking (BLINK-style) for ambiguous mentions. Entity resolution quality determines graph quality.

**3. Hybrid retrieval: graph first, vector second.**
For purely factual queries ("who is the CFO?"), traverse the graph. For analytical queries ("what are the risk patterns in recent contracts?"), use graph traversal to narrow the search space, then vector retrieval within the identified subgraph. For unstructured text analysis, vector retrieval is the primary path, with graph verification as a secondary pass.

**4. Provenance tagging at retrieval time.**
Every fact retrieved from the graph carries its source document, extraction timestamp, and confidence score. The agent cites specific entities, not chunks. This makes trace-to-answer a first-class operation.

**5. Graph-aware answer verification.**
After generation, parse the answer for entity mentions. Resolve each mentioned entity against the graph. Flag any entity that doesn't exist in the graph, or whose relationship contradicts the stated claim. This catches conflation errors (Acme Inc. vs Acme LLC) that vector retrieval cannot detect.

```python
# Minimal entity grounding pipeline
from your_graph_lib import KnowledgeGraph
from your_embed import embed_model

class EntityGroundingPipeline:
    def __init__(self, graph: KnowledgeGraph, vector_store, llm):
        self.graph = graph
        self.vector_store = vector_store
        self.llm = llm

    def answer(self, question: str) -> dict:
        # Step 1: Extract entities from the question
        entities = self._extract_entities(question)  # NER + linking

        # Step 2: Graph traversal for factual grounding
        graph_facts = []
        for entity in entities:
            facts = self.graph.query_neighbors(entity, depth=2)
            graph_facts.extend(facts)

        # Step 3: Optional vector fallback for analytical queries
        if not graph_facts:
            chunks = self.vector_store.search(question, top_k=8)
            graph_facts = [{"type": "vector_chunk", "content": c} for c in chunks]

        # Step 4: Generate with graph-grounded context
        context = self._format_context(graph_facts)
        answer = self.llm.generate(f"Question: {question}\nContext: {context}")

        # Step 5: Verify answer entities against graph
        answer_entities = self._extract_entities(answer)
        violations = self._verify_entities(answer_entities, self.graph)

        return {
            "answer": answer,
            "graph_facts": graph_facts,
            "violations": violations,  # empty = verified
            "verified": len(violations) == 0
        }

    def _verify_entities(self, entities, graph):
        """Check each answer entity against the knowledge graph."""
        violations = []
        for ent in entities:
            canonical = graph.resolve_entity(ent.text)
            if canonical is None:
                violations.append(f"Unknown entity: {ent.text}")
            elif ent.claimed_relationship not in graph.get_relationships(canonical):
                violations.append(
                    f"Unsupported claim: {ent.text} --[{ent.claimed_relationship}]--> ?"
                )
        return violations
```

## Receipt

> Receipt pending — 2026-07-02

## See also

- [S-100 · Agentic RAG](s100-agentic-rag.md) — retrieval planning and query rewriting (the agent loop that *uses* the grounding layer)
- [S-374 · The Agentic RAG Gap](s374-the-agentic-rag-gap.md) — the multi-hop failure modes this pattern directly addresses; self-check loops validate graph-grounded answers
- [S-212 · Semantic Output Validation Gate](s212-semantic-output-validation-gate.md) — the post-generation validation layer that complements entity-level verification
- [S-314 · Agent Memory Layer Architecture](s314-agent-memory-layer-architecture.md) — the three-tier memory taxonomy (episodic / semantic / procedural) where the knowledge graph occupies the semantic tier
