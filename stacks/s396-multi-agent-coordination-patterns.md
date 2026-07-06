# S-396 · Multi-Agent Coordination: Deterministic Orchestration Over Emergent Swarms

The moment two agents need to share work, handle a failure, or coordinate state — the tempting "throw them in a room and let them figure it out" approach produces politeness loops, hallucination chains, and non-deterministic behavior that no prompt engineering fixes. The field is converging on a hard lesson: wrap probabilistic agents in deterministic coordination.

## Forces

- **Emergent coordination fails at the worst times.** Chatroom-style agent swarms where agents negotiate freely work in demos. They collapse under production load — retries, context drift, and trust-free politeness loops compound into silence that looks like success
- **Context degradation kills reasoning.** Models lose up to 73% of reasoning accuracy when critical information is buried in the middle of a long context window — regardless of context window size. Compartmentalized agents avoid this by design
- **Pattern choice outperforms model choice.** Smaller specialized models running a well-chosen coordination pattern outperform larger models in a poorly-coordinated swarm. The coordination layer is the leverage point
- **The stack stratifies.** Specialized tools for sandboxing, orchestration, memory, and observability are replacing monolithic frameworks — not because monolithics don't work, but because layer-specific failures need layer-specific mitigations

## The Move

**Treat orchestration as a deterministic state machine around probabilistic agent cores.** The agent decides *what to do*; the orchestrator controls *when, in what order, and with what guardrails*.

Five production-vetted patterns, ordered from simplest to most complex:

1. **Sequential (Pipeline):** A → B → C in fixed order. Unix pipes for agents. Use when steps have clear dependencies and each agent transforms output for the next.
2. **Hierarchical (Supervisor):** A supervisor agent delegates to specialized workers, synthesizes results. Use for complex tasks requiring domain expertise separation. The supervisor is *not* a chatroom moderator — it makes routing decisions, not conversational ones.
3. **Fan-out / Fan-in:** One agent spawns N parallel workers on subtasks, then synthesizes. Use when subtasks are independent and latency matters.
4. **Peer Network:** Agents communicate directly on shared tasks. Use for systems where agents have complementary but equal roles (e.g., writer + critic).
5. **Multi-Agent Debate:** Agents produce contradictory outputs, a critic or voting mechanism selects the best. Use for high-stakes decisions requiring adversarial verification.

**The critical discipline:** keep the coordination logic *outside* the agent's prompt. If an agent is deciding who does what, you've built a meta-agent with the same failure modes as a monolith. The agent should receive a *task assignment*, not participate in *workflow negotiation*.

## Evidence

- **Benchmark data:** ChatDev achieves 33.3% correctness on real programming tasks when agents self-coordinate. AppWorld shows 86.7% failure on cross-app workflows in open multi-agent settings. Logistics systems using structured patterns show 27% throughput gains and 22% cost reduction — demonstrating that pattern discipline pays off where free-form coordination fails — [Thread Transfer, July 2025](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns/)
- **HN field report:** "The common trap I've seen: throwing agents into a 'chatroom' style collaboration with a manager agent deciding everything. Locally this gets messy fast — politeness loops, hallucination chains, non-deterministic behavior, especially with smaller models. My take: treat agents more like microservices, with a deterministic orchestration layer around the probabilistic cores." — HN user Evening-Arm-34 on r/LocalLLaMA, describing production experience with multi-agent setups — [Reddit r/LocalLLaMA, 2025](https://www.reddit.com/r/LocalLLaMA/comments/1pzv687/the_agent_orchestration_layer_managing_the_swarm/)
- **Enterprise production stack:** Opensoul runs a 6-agent marketing agency (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) using Paperclip orchestration with scheduled heartbeats, explicit work queues, and delegated reporting — not free-form agent negotiation — [Show HN, March 2025](https://news.ycombinator.com/item?id=47336615)
- **Context degradation evidence:** Long-context windows degrade up to 73% on reasoning tasks when critical information is buried mid-context. Multi-agent compartmentalization solves this by giving each agent focused context and synthesizing summaries — [Comet Blog / Agent Engineering](https://www.comet.com/site/blog/multi-agent-systems)

## Gotchas

- **The supervisor is not a router.** If your supervisor agent is just another chat participant, you have the same problem at a different layer. Supervisor decisions should be explicit routing rules, not LLM-generated negotiation
- **Adding agents does not always improve output.** ChatDev's 33.3% correctness vs. a well-structured single-agent baseline proves that multi-agent overhead can hurt. Only split when agents have *distinct, non-overlapping capabilities* that justify the coordination cost
- **Silent failure is the dominant failure mode.** Agents that agree with each other produce confident wrong answers. Output validators between every agent boundary catch this; trust between agents does not
- **Evaluation at multi-agent scale requires HITL.** Amazon's evaluation framework for agentic systems flags human-in-the-loop as critical for multi-agent complexity — automated metrics fail to catch coordination failures that are obvious to humans — [AWS ML Blog, 2025](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
