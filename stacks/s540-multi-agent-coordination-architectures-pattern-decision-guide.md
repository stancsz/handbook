# S-540 · Multi-Agent Coordination Architectures: When Each Pattern Earns Its Overhead

[Most teams split agents by role (a "researcher," a "writer") and hope they collaborate. They rarely think about coordination topology until the system loops, contradicts itself, or costs $8/task. The coordination pattern — hierarchical, orchestrator-worker, pipeline, or peer — is the load-bearing architectural decision. Get it wrong and you inherit failure modes that don't show up until production load.]

## Forces

- **Coordination overhead compounds with task complexity.** Every hop between agents is a round-trip LLM call, a potential failure point, and a latency multiplier. Peering 5 agents in a mesh means 10 bilateral calls before anyone does real work.
- **The pattern you choose shapes every failure mode.** Hierarchical systems fail through a single point of failure (the director). Peer systems fail through inconsistency (agents diverge mid-task). Pipeline systems fail through error propagation (a bad output at step 2 corrupts everything downstream).
- **Real production systems show high failure rates.** AppWorld benchmarks show 86.7% failure on cross-app workflows. ChatDev achieves 33.3% correctness on real programming tasks. The failures are predominantly in coordination, not in individual agent capability.
- **Inference cost compounds per hop.** Complex multi-agent tasks cost $5–8 in inference alone — before infrastructure and tooling overhead. The coordination pattern determines how many hops you need.

## The move

**Match the coordination topology to the task structure, not to the team/org chart.**

**Hierarchical (director → specialists):** Best when one agent owns the outcome and specialists are interchangeable tools. The director decomposes, assigns, and synthesizes. Failure is contained at the specialist level unless the director fails. Use when tasks require a single coherent output.

**Orchestrator-worker:** Best when the number of sub-tasks is unknown at runtime and must be dynamically discovered. The orchestrator decides *what* to do next based on partial results. Use for open-ended research, investigation, or triage tasks.

**Pipeline (serial stages):** Best when the output of step N is the strict input of step N+1, and each stage is well-defined. No branching, no dynamic discovery. Use for editorial workflows (draft → review → publish) or document processing (parse → extract → validate).

**Peer-to-peer (negotiated):** Best when agents have equal authority and the solution requires consensus — e.g., trading agents, multi-party negotiation, adversarial synthesis. The hardest to get right because you must define the convergence protocol. Use sparingly.

**General heuristic:** If you can't write the coordination protocol in 5 sentences, you're probably trying peer-to-peer when you need a director.

## Evidence

- **Gartner (2025):** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. 40% of agentic AI projects will be canceled by end of 2027 due to unclear business value. — [Gartner via RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Benchmark data (AppWorld, 2025):** 86.7% failure rate on cross-app workflows. ChatDev achieves 33.3% correctness on real programming tasks. However, logistics-domain deployments report 27% throughput gains and 22% cost reduction. — [BYaiteam blog](https://byaiteam.com/blog/2025/11/14/multi-agent-systems-architectures-coordination-use-cases/)
- **Opensoul case (HN, 2026):** A production marketing agent stack with 6 agents organized as a real agency: Director (strategy/coordinator), Strategist, Creative, Producer, Growth Marketer, Analyst. Each runs on scheduled heartbeats, checks work queues, delegates to teammates. Uses Paperclip orchestration. — [HN Show](https://news.ycombinator.com/item?id=47336615)
- **Cost data (The Operator Collective, 2025):** Complex multi-agent tasks compound to $5–8 in inference cost per task before infrastructure overhead. A moderate production setup (~100–200 tasks/day) runs €30–80/month in API costs — the smallest line item. Infrastructure + tooling adds €0–40 more. ROI of €0.70/hour of work saved. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-cost-breakdown)

## Gotchas

- **Designing by job title, not by task structure.** "Researcher" and "Writer" agents sound intuitive but create ambiguity about who owns the output and how disagreements are resolved. Prefer patterns where the output ownership is unambiguous.
- **Adding agents reduces reliability per agent.** Every additional agent in a coordination graph multiplies the failure surface. RaftLabs data: 89% of teams have tracing infrastructure, but only 52% have actual evaluation harnesses — meaning most teams can't detect when a coordination failure occurred versus when an individual agent failed.
- **Pipeline systems propagate errors silently.** If step 2 produces subtly wrong output, downstream stages will confidently elaborate on the error. Add a validation gate after each pipeline stage before passing output to the next.
- **Peer systems need an explicit convergence protocol.** Without one, agents diverge or loop indefinitely. Define: how many rounds? what triggers a final answer? what happens on disagreement?
