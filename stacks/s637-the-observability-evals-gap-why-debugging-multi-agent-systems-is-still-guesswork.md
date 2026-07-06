# S-637 · The Observability–Evals Gap: Why Debugging Multi-Agent Systems Is Still Guesswork

Every team has dashboards. Fewer than half have evals. The result: agents in production are observable in the wrong dimension — you can see what happened, but not whether it was right.

## Forces

- **Tracing ≠ evaluation.** LangSmith, Phoenix, and custom log pipelines give you execution traces, token counts, and latency waterfalls. None of that tells you if the agent's reasoning was sound, if the retrieved context was actually relevant, or if two agents made contradictory decisions in the same workflow.
- **The multi-agent explosion amplifies the gap.** A single-agent pipeline is hard to debug; a 4-agent orchestrator-worker workflow has combinatorial failure modes. A trace showing Agent C received bad context from Agent B is a starting point, not an answer — you still need to know whether Agent B's tool selection was wrong, its prompt drifted, or the retrieval query was ambiguous.
- **Evals are expensive and slow.** Good agent evals require golden datasets, reference outputs, and human-in-the-loop scoring for edge cases. Teams deprioritize them because they don't block deployments. They block deployments later, expensively.
- **Cost compounds invisibly.** A 4-agent complex-task workflow costs $5–8 per run (RaftLabs, 2025). If you can't measure whether the output is correct, you're burning that per-run cost on guesswork — and Gartner estimates 40% of enterprise agentic AI projects will be cancelled by end of 2027 due to unclear business value.
- **The shift left never happened.** In traditional software, testing moved left into CI. In agentic systems, evals are still post-hoc or absent — largely because the field hasn't standardized what "passing" means for a system that can produce correct output via incorrect reasoning.

## The move

Treat evaluation as a first-class infrastructure layer, not a post-launch checkbox. The teams succeeding at multi-agent production have converged on a specific structure:

- **Golden dataset before first deployment.** Curate 50–100 representative task examples with known-good outputs. Cover the critical path and the known edge cases. This is your baseline, not your ceiling.
- **Layered eval metrics.** Automated metrics (RAGAS for retrieval quality, exact-match for extraction tasks, BLEU/BERTScore for generation) catch regressions fast. Human-in-the-loop scoring catches the failures automated metrics miss — specifically: reasoning soundness, tool selection appropriateness, and inter-agent handoff quality.
- **Eval at every agent boundary.** This is the highest-leverage intervention. Each agent-to-agent handoff should be validated: did the receiving agent get a schema-conformant input? Did the previous agent's output actually address the subtask? Untyped handoffs are the fastest way to introduce silent failures that compound across the workflow.
- **HITL for multi-agent specifically.** Amazon's agentic systems team found that human-in-the-loop is *more* critical for multi-agent than single-agent — inter-agent coordination failures, conflict resolution quality, and collective behavior toward business objectives are dimensions that automated metrics routinely miss.
- **Continuous eval in production, not just staging.** Drift happens: retrieval quality degrades as documents change, prompts drift under fine-tuning, tool schemas evolve. Run a lightweight eval sample on every Nth production request to catch drift before it becomes a user-facing failure.
- **Cost-per-eval as a metric.** Track cost per successful task, not just token spend. A $0.30 task that requires 3 retries costs $0.90 — that's an eval signal, not just a cost control issue.

## Evidence

- **Industry survey:** 89% of teams building multi-agent systems have observability tooling; only 52% have formal evals. The gap explains why debugging is described as "mostly guesswork" across practitioner discussions. — [RaftLabs: Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
- **Enterprise deployment case study:** Teams operationalizing agents at scale found that P95/P99 latency matters more than mean response time — users remember the slowest experience. Caching exact-match prompt outputs and semantically similar query results materially improved both latency and cost. — [Medium/Data Science Collective: Lessons Learned from Building Enterprise AI Agents for Millions of Users](https://medium.com/%40prdeepak.babu/lessons-learned-from-building-enterprise-ai-agents-for-millions-of-users-cfd6a1ad3f56), December 2025
- **AWS / Amazon engineering post:** For multi-agent evaluation specifically, human-in-the-loop becomes critical because automated metrics fail to capture: inter-agent communication quality, conflict resolution appropriateness, and whether the collective agent behavior serves the intended business objective. HITL provides oversight for dimensions "difficult to quantify through automated metrics alone." — [AWS ML Blog: Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon), 2025–2026
- **2025 operationalization report:** Xpress AI's fifth agent framework attempt succeeded where the first four failed — not because of better models, but because they stopped treating the framework as "magic" and started treating it as distributed infrastructure with explicit SLA contracts between components. — [Xpress AI: Operationalizing AI Agents: Lessons from 2025](https://xpress.ai/blog/2025-agent-lessons), January 2026

## Gotchas

- **LangSmith and Phoenix give you traces, not judgments.** You can see that Agent B called the wrong tool, but you need an eval to know whether it was a reasoning failure, a prompt drift, or a tool schema ambiguity. Trace visibility without eval judgment is a dashboard with no alerts.
- **Synthetic golden datasets degrade over time.** If your document corpus changes, your reference answers become stale. Re-annotate or use LLM-as-judge on a sample to catch drift — don't assume the golden dataset is still golden.
- **Multi-agent eval is not N × single-agent eval.** The interaction failures (conflicting recommendations, handoff schema violations, coordination deadlocks) don't appear in single-agent test runs. You need integration-level eval runs that exercise the full workflow.
- **The observability vendor pitch ≠ production readiness.** Having LangSmith or Phoenix installed is necessary but not sufficient. The question is whether your team has defined what "good" looks like, encoded it in an eval suite, and is running it continuously. Most teams haven't.
