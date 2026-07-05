# S-595 · Agentic Governance Stack: Enterprise Patterns and Production Cost Engineering

The single-agent demo works fine. The moment you run 6 agents across a business workflow, you have a coordination problem, an authorization problem, a cost control problem, and an audit problem — simultaneously. Enterprise teams with 60+ deployments are converging on a layered governance architecture that handles all four.

## Forces

- **"Fail-open" is fine until agents trigger payments, deploy code, or modify production data.** Most agentic systems log after the fact. High-stakes actions need runtime enforcement, not post-hoc auditing.
- **Cost control is an afterthought until your first runaway loop.** Teams report costs from $15 in 10 minutes to $47,000 over 11 days. The variance is not outliers — it's a missing control layer.
- **Evaluation can't be retrofitted.** Quality drift happens silently. Without continuous automated evaluation baked into CI, you discover degradation only when users report it.
- **Tool integration lock-in is the real cost center.** Orchestration frameworks are swappable. Your custom REST wrappers, internal API connectors, and tool schemas are not — and rebuilding them is where teams get stuck.

## The Move

Build a layered governance architecture around the agentic loop — not bolted on after.

**Certification / output governance (TrustGate pattern):**
- Run agent outputs through a certification layer before external delivery
- Verify outputs against policy, format, safety, and factual consistency
- Block or quarantine outputs that fail certification criteria
- Audit trail for compliance: who triggered the agent, what it saw, what it returned

**Runtime authorization (fail-open → fail-closed):**
- Agent proposes action → authorization layer evaluates → execution proceeds or blocks
- Define operational boundaries: which agents can call which tools, with what parameters
- Separate read vs. write permissions; escalation paths for high-stakes actions
- "Most agent systems are fail-open: the model proposes, the tool executes, logs are written after the fact." — runtime authorization layer turns this into propose → authorize → execute → log

**Context and memory governance (Pillar pattern):**
- Centralized context management for agent memory across the organization
- Semantic layer on top of retrieval — agents don't get raw vectors, they get policy-filtered context
- Data provenance tracking: which data sources informed which outputs
- Session-level and cross-session memory with configurable retention and expiry

**Cost engineering:**
- Hard budget enforcement with per-agent, per-workflow spend limits
- Prompt caching as the first lever — 60–85% of AI spend is recoverable through disciplined caching alone (Zylos Research, 2026)
- Model routing: fast/small models for classification and routing; large models for synthesis and reasoning
- Circuit breakers: hard timeout on agent loops, automatic escalation on cost threshold breach
- Production cost benchmark: enterprises averaging $85,521/month in AI operational costs as of 2025 (Zylos Research)

**Automated evaluation in CI (Shopify pattern):**
- Build evaluation from day one, not when quality drift is noticed
- LLM-as-judge: compare outputs against known-good examples, score quality criteria per turn
- Multi-turn evaluation: does the agent carry context correctly across turns, recover from mistakes, reach the user's goal?
- Judge calibration: collect human labels, run optimization algorithm to align judge outputs with human assessments
- Component-level eval: test retrieval separately from generation; check if agent actually used retrieved context

## Evidence

- **HN Show HN (2025):** Cohorte AI open-sourced a 6-library enterprise governance stack (TrustGate, Sentinel, Pillar, and 3 others) from 60+ enterprise deployments. Built to solve certification, authorization, context management, and observability as a unified system — not a pile of disconnected tools. — https://news.ycombinator.com/item?id=47860859
- **Shopify Engineering (Aug 2025):** Sidekick moved from simple tool-calling to a full agentic platform with Anthropic's agentic loop, LLM-based evaluation frameworks, and GRPO training. Key lesson: automated evaluation must be built from the beginning, not retrofitted. — https://shopify.engineering/building-production-ready-agentic-systems
- **Zylos Research (May 2026):** Production AI agent costs range from $15 in 10 minutes (small loop) to $47,000 over 11 days (runaway multi-agent). 60–85% of spend is recoverable through prompt caching, model routing, and hard budget enforcement. Enterprises average $85,521/month in AI operational costs. — https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics
- **Technspire (Dec 2025):** Four categories consistently shipped to production in 2025: developer tooling, internal operations automation, research and analysis, and tool-augmented LLMs. What failed: autonomous customer-facing agents with unbounded scope, and multi-agent systems without clear coordination patterns. — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons
- **MLflow (2026):** Top evaluation tools compared — MLflow for broadest metric coverage and judge alignment, DeepEval for pytest-style CI, Ragas for RAG-focused metrics, Arize Phoenix for teams extending ML observability. Judge calibration (aligning LLM judges to human labels via optimization algorithms) is the key to reproducible evaluation. — https://mlflow.org/top-5-agent-evaluation-frameworks

## Gotchas

- **Don't build evaluation after deployment.** By the time users report quality problems, drift has compounded. A judge trained on baseline outputs catches regressions before they reach users.
- **Don't skip cost circuit breakers in dev.** Runaway loops look fine locally with small context. They become $47K incidents in production with real data and longer sessions.
- **Don't treat orchestration as the hard problem.** Teams spend weeks evaluating LangGraph vs. CrewAI when the real lock-in is tool integrations. Choose orchestration by team familiarity; invest heavily in the tool layer.
- **Don't over-engineer memory before you have enough agent interactions to tune it.** Three-tier memory with hybrid retrieval sounds impressive; similarity thresholds and merge strategies only get tuned with real production data.
- **Multi-model routing is standard practice now.** Teams average 2.8 models per agentic system — not for complexity, but for cost optimization. Fast models for routing and classification; large models for synthesis.
