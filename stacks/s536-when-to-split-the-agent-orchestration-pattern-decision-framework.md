# S-536 · When to Split the Agent: The Orchestration Pattern Decision Framework

[Your single agent handles 8 tools and 12 steps. It still works — but response time is climbing, tool-call accuracy dropped below 80%, and when it fails, the whole thing fails together. You know you should split it, but into what? A pipeline? A hierarchy? Peer agents? The choice compounds for months or years. The difference between a 27% throughput gain and a 33% correctness score comes down to picking the right pattern before you build.]

## Forces

- **Single-agent complexity hits a wall around 10 tools and 5+ steps.** Tool selection accuracy drops below 90% past 10 tools, context windows compress and degrade, and a single failure cascades through the entire workflow. You need to split — but the splitting strategy determines whether complexity becomes manageable or multiplies.
- **Pattern choice is the highest-leverage decision and the hardest to reverse.** Multi-agent systems are expensive to refactor once built. Switching from a hierarchical to a peer-to-peer model mid-production means rewriting coordination logic, re-training agents on handoff protocols, and re-validating every edge case. Choosing wrong costs 6–12 months of engineering time.
- **Inconsistent inter-agent data is where multi-agent systems actually fail.** The agents themselves are usually reliable. What breaks is the unstructured data passed between them — the format of a handoff, the schema of a shared context object, the error that silently propagates because no validator catches it. Strong teams validate at every boundary.

## The Move

**Choose your orchestration pattern based on task topology — not preference.**

### The four production patterns and their triggers

1. **Pipeline (Sequential)** — Use when steps have strict order and each transforms the output of the previous. Equivalent to Unix pipes. Best for: document processing (extract → classify → extract structured → validate). Bottleneck risk at the slowest step.

2. **Hierarchical** — Use when a director/manager agent decomposes work and delegates to specialized workers. Best for: marketing agencies (Director → Strategist → Creative → Producer), enterprise workflows. Central failure risk — make the director idempotent or replicate it.

3. **Orchestrator-Worker** — Use when a central agent plans a complex task but delegates granular execution. Best for: research tasks (orchestrator plans queries, workers search/retrieve, orchestrator synthesizes). Gives you the flexibility of planning with the parallelism of delegation.

4. **Peer-to-Peer** — Use when agents share a flat namespace and collaborate as equals. Best for: brainstorming, peer review, debate, critique loops. Requires the most governance overhead. ChatDev achieves 33.3% correctness with this pattern on coding tasks — it's powerful but fragile.

### The decision tree

```
Task has strict step order?
  YES → Pipeline
  NO  → Task needs domain specialization?
          YES → Hierarchical (with director)
          NO  → Sub-task decomposition possible?
                  YES → Orchestrator-Worker
                  NO  → Peer-to-peer or keep single agent
```

### Hard rules for multi-agent production

- **Validate at every boundary.** Every handoff passes through an output validator that enforces schema, policy, and safety limits. Validators must be deterministic and fail loudly — silent failures at inter-agent boundaries become systemic failures.
- **Use critic/self-verifier loops at decision points.** Before a handoff executes, a critic agent checks for completeness, internal consistency, and constraint adherence. Reduces error propagation without adding evaluation-style overhead.
- **Instrument handoff latency and failure rate per edge.** Every inter-agent call should be traced. If Agent A → Agent B fails more than 5% of the time, the handoff schema is wrong, not the agents.
- **Start with the fewest agents that solve the problem.** Teams tend to over-decompose. Three agents that do their jobs well outperforms ten agents with unclear boundaries.
- **Run a chaos test: kill one agent mid-workflow.** If the system can't recover gracefully, the handoff contracts are too loose.

## Evidence

- **Engineering blog (RaftLabs):** Multi-agent systems in production show 3× faster task completion and 60% better accuracy when the correct pattern is used. Gartner tracked a 1,445% surge in multi-agent inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **Engineering blog (Thread Transfer):** Logistics systems demonstrate 27% throughput gains and 22% cost reduction with multi-agent pipelines. However, ChatDev achieves only 33.3% correctness on real coding tasks, and AppWorld shows 86.7% failure on cross-app workflows — pattern choice matters more than model capability. — [https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)

- **Technical guide (Meta Intelligence):** LangGraph (fine-grained state machine control, 90K+ GitHub stars) is the production standard for complex workflows; CrewAI (role-based, intuitive, 20K+ stars) is the fastest path to working prototypes; AutoGen/AG2 (conversation-driven) excels in negotiation scenarios but carries a steeper learning curve. — [https://www.meta-intelligence.tech/en/insight-ai-agent-frameworks](https://www.meta-intelligence.tech/en/insight-ai-agent-frameworks)

## Gotchas

- **Under-decomposing is more common than over-decomposing.** Teams keep adding tools to a single agent because splitting feels expensive. By the time they split, they've built enough path-dependency that refactoring costs more than splitting earlier would have.
- **Peer-to-peer sounds elegant but governance is brutal.** Every peer agent needs a clear charter, a bounded domain, and explicit exit criteria. Without it, you get agents looping on each other or duplicating work with no convergence signal.
- **Hierarchical systems are only as good as the director.** A bad director — one that decomposes tasks incorrectly or creates too much or too little granularity — propagates errors to every worker. Test the director's decomposition quality with edge cases before scaling the worker pool.
- **Multi-agent inference costs compound fast.** Each agent call is an LLM call. A 4-step pipeline with 3 parallel workers per step can cost 5–8× more per task than a single-agent equivalent. Measure cost per task before deploying, not after.
- **Remote MCP server handoffs introduce latency and failure modes.** If agents communicate via MCP over the network, cold starts and network errors become part of your failure budget. Snapshot-based orchestration or warm pools mitigate this.
