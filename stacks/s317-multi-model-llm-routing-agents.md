# S-317 · Multi-Model LLM Routing: The Cost Architecture Underneath Every Agent Stack

Single-frontier-model agent stacks are a budget leak dressed as a design decision. Routing requests by task complexity across model cost tiers — Haiku for classification, Sonnet for standard work, Opus for architecture reviews — cuts costs 60–87% without quality loss. The mechanism is mature, the tooling is commoditized, and the gap between teams that do it and teams that don't is widening fast.

## Forces

- **The 100x price spread makes naive routing expensive.** Frontier models run $5–25/MTok while efficiency models run $0.10–1/MTok. An agent doing 2,000 dispatches/month at full frontier pricing costs ~$2,847/mo; routing by task type brings that to ~$370/mo — a pattern validated across multiple real stacks.
- **Agent workloads are heterogeneous; single-model stacks aren't.** A typical agent pipeline touches classification, code generation, summarization, tool calling, creative writing, and architecture decisions — each with radically different capability requirements. One model serving all is either overpaying for simple tasks or under-performing on hard ones.
- **Routing intelligence was historically fragile; it isn't anymore.** Early work (FrugalGPT, RouteLLM) showed the concept worked but the classifiers were brittle. 2025 production data shows routing now matches or beats single-model quality on well-defined task splits, with LLMRouterBench providing unified evaluation benchmarks to validate this.
- **The AI gateway pattern decouples routing from application logic.** Abstracting "which model" behind a shared gateway module means routing rules can evolve without touching agent code — enabling per-task, per-turn, or even per-agent-role routing with a single configuration change.

## The move

1. **Classify agent tasks by cognitive demand.** Create a dispatch taxonomy: classification/routing (cheapest), standard tool-use and QA (mid-tier), architecture decisions and code review (frontier). Route each tier to its appropriate model family.
2. **Implement an AI gateway as the single routing boundary.** LiteLLM, AWS Bedrock Intelligent Prompt Routing, or a custom classifier — whichever, all agent dispatch goes through one place. This enables runtime model swaps without touching agent logic.
3. **Use role-based routing in multi-agent systems.** Assign fixed models per architectural role: planner always gets frontier, executor gets mid-tier, classifier gets cheapest. Per-turn routing within executor turns handles the trivial cases (e.g., a file-read step that doesn't need Sonnet).
4. **Validate routing quality with evals, not intuition.** LLMRouterBench or internal task-specific benchmarks confirm routing decisions maintain quality. Semantic similarity caching catches repeated queries at zero model cost.
5. **Start with static routing, graduate to dynamic.** Hard-code simple splits first (task type → model) before investing in classifier-based routing. The first 60–70% of cost savings come from obvious splits; marginal gains from smarter classifiers require more infrastructure.

## Evidence

- **Engineering blog / case study:** A production multi-agent code system reduced monthly cost from ~$2,847 to ~$370 by routing 50% of dispatches to Sonnet, 30% to Codex, and 10% each to Opus and Flash — achieving 87% cost reduction without quality regressions. Per-dispatch overhead from the V8 dispatcher was <2ms. — [Mindra/MIT AI Agent Index](https://mindra.co/blog/multi-model-routing-how-to-choose-the-right-llm-for-every-task)
- **Research (Stanford/TMLR, UC Berkeley):** FrugalGPT demonstrated up to 98% cost reduction via cascade routing; RouteLLM showed 85% reduction using matrix factorization classifiers. Both are validated by LLMRouterBench (ACL 2026) as benchmarks for routing quality. — [Zylos Research](https://zylos.ai/research/2026-05-06-ai-agent-multi-model-orchestration-runtime-selection/)
- **Enterprise survey (Cleanlab, 1,837 respondents):** Only 5% of engineering leaders had AI agents live in production — but among those who did, multi-model routing was the single most cited cost control mechanism. 70% of regulated enterprises rebuild their AI stack every three months, with routing logic being the most frequently refactored component. — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Framework support:** LangGraph supports per-node model assignment, enabling planner-executor routing as a first-class graph configuration. CrewAI supports model selection per agent role. AWS Bedrock Intelligent Prompt Routing provides native per-prompt quality prediction with 60% cost reduction on qualifying workloads. — [JetThoughts/LangGraph comparison](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

## Gotchas

- **Routing classifiers can hurt if trained on the wrong distribution.** LLMRouterBench shows that many commercial routers fail to beat simple baselines under unified evaluation. Start with rule-based splits before investing in ML classifiers.
- **Reranking and long-context steps break cheap routing.** Anything that needs to read 20 chunks before answering is a poor candidate for mid-tier routing — route such steps to frontier, or fix the retrieval first.
- **Caching and routing interact.** Semantic caching (69% hit rate reported) stacks multiplicatively with routing — but cache invalidation on agentic workflows is harder than on single-turn chat because the "same" query may arrive in different forms.
- **Context length differences affect total cost, not just per-token price.** Haiku's 200K context vs Sonnet's 200K vs Opus's 200K matters less than the per-token differential, but truncation behavior at context limits can cause quality regressions that routing evals won't catch if the eval doesn't use long inputs.
