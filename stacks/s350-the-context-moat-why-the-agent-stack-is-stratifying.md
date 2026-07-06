# S-350 · The Context Moat: Why the Agent Stack Is Stratifying

The agent stack is fragmenting into six distinct layers — and the layer teams think is their moat (the model) is the wrong one. Context sits in the highest lock-in zone, and the teams building durable agentic products know it. The stack is stratifying whether you're ready for it or not.

## Forces

- **37% of enterprises now run five or more AI models in production** — single-provider lock-in is the new single-cloud risk, and teams are deliberately distributing across layers to avoid it.
- **40%+ of agentic AI projects will be canceled by end of 2027** due to unclear business value, not technical failure — the winners are the ones who build where value actually compounds (context, not models).
- **Model prices collapsed 99x in 18 months** — commoditization is accelerating. Claude Opus and GPT-5 are table stakes; they don't differentiate your product in 2026.
- **Sandboxing is its own layer now.** E2B, Modal, Shuru, Firecracker wrappers, and Google GKE Agent Sandbox (November 2025) are converging on isolation-as-a-service. This is no longer an ops afterthought.
- **Context is the highest-lock-in, hardest-to-rebuild zone.** Your organizational world model — how decisions get made, what the knowledge graph encodes, what the embedding space captures — takes years to accumulate and can't be swapped out with an API key.

## The Move

Treat the agent stack as six independent layers, each with its own upgrade path, vendor choice, and failure mode:

1. **Application layer** — what the user interacts with. Workflow UI, chat interfaces, Slack bots. Lowest lock-in, easiest to rebuild.
2. **Orchestration layer** — LangGraph, CrewAI, custom state machines, Temporal for durable execution. Framework choice matters less than the durability and observability guarantees underneath it.
3. **Model layer** — OpenAI, Anthropic, open-source via vLLM or Ollama. Commoditized. Route by task type, not brand loyalty. Use Haiku for routing decisions, Opus for complex reasoning, a local quantized model for tool calls.
4. **Context layer** — RAG pipelines, memory stores, semantic caches, knowledge graphs. **This is where value compounds.** Retrieval is the bottleneck: naive RAG fails ~40% of the time; fix retrieval first. Chunk at 500–1,500 tokens with 10–20% overlap. Use hybrid BM25 + dense vectors with reciprocal rank fusion. Cross-encoder rerank top-50 → keep top-5–10.
5. **Tool/execution layer** — MCP (Model Context Protocol) is becoming the standard for agent-tool coupling, displacing bespoke REST integrations. Sandboxing belongs here, not at the infra layer.
6. **Infrastructure layer** — Kubernetes, serverless GPU (Modal, Replicate), managed container sandboxes. Keep it boring; the agent value lives above it.

**Don't go monolithic at any layer.** Conflating orchestration with execution (CrewAI's default coupling), or routing with reasoning (skipping model routing entirely), creates cascading failures that are hard to debug and impossible to swap.

## Evidence

- **Blog post (Philipp Dubach, Feb 2026):** "The defensible asset in enterprise AI is not the model. It's the organizational world model." Documents the six-layer stratification thesis with McKinsey/Gartner adoption data — 23% of organizations scaling agentic AI, 39% experimenting. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion (2026):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. E2B, Modal, Shuru, Firecracker wrappers." Practitioner corroboration of the stratification trend from someone building partial-AI software development tools. — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **RAG production guide (Lushbinary, April 2026):** Documents the retrieval-as-bottleneck finding — naive RAG fails at retrieval 73% of the time, not generation. Cross-encoder reranking over hybrid search is the production standard. Chunk sizes, overlap ratios, and token budgets quantified. — [https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)

## Gotchas

- **Sandboxing is not ops — it's a security and reliability layer.** A prompt-injected instruction or a bad tool call in a shared container doesn't just affect your agent. Treat sandbox isolation as a first-class application concern, not a Kubernetes afterthought.
- **Sequencing agents by cost, not capability, is the biggest cost control lever.** A 3-agent pipeline at 100 runs/day costs ~$900/month with Opus-class models. Swapping intermediate steps to Haiku or a local quantized model can cut that by 60–80% without measurable quality degradation for routing and extraction tasks.
- **Model routing at the orchestration layer (not the application layer) prevents prompt pollution.** CrewAI v0.98+ and LangGraph both support per-node model routing — use it. Don't hardcode a single model across a multi-step workflow.
