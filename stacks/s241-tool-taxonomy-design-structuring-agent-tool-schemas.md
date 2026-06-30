# S-241 · Tool Taxonomy Design — Structuring Agent Tool Schemas for Reliable Selection

Your agent has 40 tools. The model picks the right one 70% of the time in demos. In production, with real user input and noisy contexts, it picks the right one 43% of the time — and 31% of failures are tool selection errors, not tool execution errors. The fix is not more tools. It's a taxonomy.

## Forces

- **Flat tool lists collapse under scale.** The Shopify Sidekick team identified a sharp cliff at 20-50 tools: above it, boundaries become unclear, tool combinations produce unexpected outcomes, and the system becomes difficult to reason about — not because the tools are bad, but because the model has no hierarchy to navigate. — [Shopify Engineering Blog, Aug 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **Tool descriptions compete for the model's attention.** When every tool description is at the same level of abstraction, the LLM's attention diffuses. Semantic similarity between tool names and descriptions causes mis-selection — "get_customer" vs "fetch_customer_profile" vs "retrieve_customer_data" all sound plausible for the same task.
- **Tool consolidation at the taxonomy level outperforms prompt-level instruction.** Teams that attempt to fix tool selection errors through longer, more explicit prompts typically see marginal improvement. Teams that restructure the schema — grouping related tools, adding hierarchy, collapsing redundant tools — consistently see 20-40% reduction in selection errors. — [AIThinkerLab RAG Patterns 2026](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns/)
- **The agent stack is stratifying.** HN discussion in early 2026 identified a broader pattern: the agent stack is splitting into specialized layers, and tool abstraction is emerging as its own distinct layer, separate from orchestration and execution. — [Hacker News, HN id:47114201](https://news.ycombinator.com/item?id=47114201)

## The move

Organize tools into a semantic taxonomy before worrying about individual tool quality.

**1. Collapse by intent, not by function.** Group tools that serve the same user intent even if they operate on different backends. "get_customer" and "retrieve_customer_data" collapse into one tool with a unified description and a backend dispatch parameter. A single taxonomy entry with multiple backend adapters beats two competing entries every time.

**2. Add a routing layer above raw tools.** Introduce a thin semantic router — a classifier or small LLM — that maps user intent to tool groups, then lets the agent pick within the narrowed set. This is the same pattern as agentic RAG query routing. Cuts the selection problem from 40→4 for any given task. — [Agent.nexus LangGraph vs CrewAI comparison, Nov 2025](https://agent.nexus/blog/langgraph-vs-crewai)

**3. Name tools by domain verb, not implementation noun.** "customers.list", "orders.create", "inventory.adjust" — the pattern of `resource.verb` creates an implicit taxonomy the model can infer. Avoid generic names like "query" or "get_data" that provide no semantic anchor.

**4. Tag each tool with capability metadata.** Annotate tools with `domain` (e.g., `ecommerce`, `support`, `analytics`), `requires_confirmation` (bool), `mutability` (read/write/admin), and `data_sensitivity` (public/internal/sensitive). The model uses these to prune dangerous combinations at selection time, not at execution time.

**5. Separate MCP servers by trust boundary.** Each MCP server is a trust surface. Group tools that share the same trust level into the same server, then enforce execution isolation at the server boundary. This is the emerging pattern from the agent stack stratification discussion: sandboxing as its own layer. — [Hacker News HN id:47114201](https://news.ycombinator.com/item?id=47114201)

**6. Design for tool replacement, not tool addition.** Every tool should be swappable without changing its schema contract. If "search_products" uses an internal search API today and switches to a third-party service tomorrow, the taxonomy should absorb that change with zero impact on the agent's selection logic.

## Evidence

- **Shopify Sidekick (2025):** The team hit the 20-50 tool cliff and rebuilt their tool system around explicit taxonomy and capability grouping. Key signal: "death by a thousand cuts" — individual tools work fine, but the combinatorial space of 50+ tools without hierarchy produces non-deterministic behavior. — [Shopify Engineering Blog](https://shopify.engineering/building-production-ready-agentic-systems)
- **AIThinkerLab MLOps benchmark (May 2026):** Across 47 production deployments, teams that applied knowledge-graph-based tool routing (a form of taxonomy) cut hallucination by ~62% compared to flat tool lists. Embedding model selection set the ceiling for retrieval accuracy within the taxonomy. — [AIThinkerLab RAG Patterns 2026](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns/)
- **Framework-level pattern:** LangGraph's node-based model and CrewAI's role-based agents both benefit from explicit taxonomy design — LangGraph nodes represent tool groups as logical units, while CrewAI's agent roles effectively serve as a human-readable taxonomy layer above individual tools. — [Lushbinary framework comparison, Apr 2026](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/)

## Gotchas

- **Adding a taxonomy layer adds latency.** A semantic router adds one LLM call per user turn. The ROI is positive only when tool selection error rate is high enough to cause downstream failures. Benchmark before adding it.
- **Taxonomy drift is a silent killer.** As tools are added and modified, the taxonomy rots — groups become inconsistent, tag metadata goes stale, naming conventions drift. Treat taxonomy maintenance like schema migrations, not documentation.
- **Over-collapse hides useful alternatives.** Merging "send_email" and "send_sms" into one "notify_customer" tool works until you need to send both — now the agent must make a second call, or the tool must return a list. Test the taxonomy against the *distribution* of real user tasks, not idealized single-intent tasks.
- **Model-specific tool selection behavior varies.** The same taxonomy may perform differently across models. GPT-4o's tool selection differs from Claude 3.5's in edge cases. Test the taxonomy against your target model, not just GPT-4.
