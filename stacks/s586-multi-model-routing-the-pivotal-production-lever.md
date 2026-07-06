# S-586 · Multi-Model Routing — The Pivotal Production Lever

When you first build an agent, you pick one model and go. After a few months in production, you realize the single-model choice was a tax you didn't know you were paying. The teams that cut LLM costs 70-90% didn't change models — they changed the routing architecture.

## Forces

- **Agents compound token usage in ways single calls don't.** A single agent call isn't expensive. But agents retry, chain, stuff context windows with conversation history, and spawn sub-tasks. The compound is invisible until you look at the bill.
- **Task complexity is wildly uneven, but models are not.** Routing a "is this email a support ticket?" classification to Claude Opus costs 30x what it needs to. Most production agent tasks are actually simple classification, extraction, or formatting jobs.
- **Quality gates catch bad outputs before they propagate, but they also catch expensive models doing cheap work.** A well-placed quality gate does double duty: it catches hallucinations AND prevents $50 Opus calls answering questions a $3 Haiku call could handle.
- **Context management is cost management.** Every token you trim from a prompt or history is a token you don't pay for twice (input + output on many APIs). Most teams never audit context hygiene until they're staring at a $5K monthly bill.

## The move

Build a **task-classification router** upfront that evaluates each incoming request and routes it to the cheapest capable model. The routing logic is not another agent — it's a lightweight classifier or ruleset that runs before the main agent loop.

- **Define task tiers explicitly.** Tier 1 (classification, routing, deduplication) → Haiku-class or fast local model. Tier 2 (summarization, formatting, SEO analysis) → Sonnet-class. Tier 3 (reasoning, code generation, complex synthesis) → Opus/GPT-5 class. This alone can shift 60-70% of token volume to cheaper tiers.
- **Use a lightweight classifier, not an LLM, for routing.** A simple keyword match, regex, or small fine-tuned classifier costs <$0.001 per call vs. $0.01-0.05 for an LLM router. One practitioner explicitly warned against using an LLM as the router — it defeats the purpose.
- **Implement a quality gate after tier-1 routing.** Route to Haiku, check output against a schema validator. If it fails or confidence is low, escalate to Sonnet. If Sonnet output still fails validation, escalate to Opus. This cascade means only the hardest 5-10% of tasks hit the expensive tier.
- **Manage context as a first-class cost variable.** Trim conversation history aggressively (keep last N turns, summarize older context). Enforce max context budgets per task type. Audit token usage per agent, not just total spend — the aggregate hides which agents are wasteful.
- **Track cost per task outcome, not just per token.** A $0.50 Opus call that resolves a support ticket in one shot is cheaper than three $0.05 Sonnet calls that each need human review. Measure end-to-end resolution cost, not inference cost.
- **Set per-agent monthly budget caps with automatic model degradation.** When an agent hits 80% of its monthly budget, force it to route everything to the next tier down. This prevents runaway costs during spikes or prompt injection loops.

## Evidence

- **Case study (solopreneur, 11 agents):** Reduced monthly LLM spend from **$2,847 to $370** (87% reduction) by implementing multi-model routing with quality gates across 11 production agents. Content generation moved from Opus to Sonnet for drafting, Haiku for classification. Budget caps prevented runaway costs during a prompt injection attack. — [Vincent van Deth, AI Architect](https://vincentvandeth.nl/blog/real-cost-ai-agents-production), December 2025
- **Industry data:** Nearly 40% of enterprises now spend over $250,000 annually on LLMs, with H1 2025 enterprise LLM spend reaching $8.4 billion. Only 63% of organizations actively track AI spend, meaning cost overruns often go undetected until they're structural. — [Vincent van Deth aggregation of enterprise data](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Amazon engineering:** Multi-agent evaluation requires human-in-the-loop (HITL) oversight specifically because increased complexity creates unexpected emergent behaviors that automated metrics miss — including cost escalation from agent loops. Evaluated agent specialization, inter-agent communication, and conflict resolution strategies to catch cost-inefficient agent configurations before production. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon), 2025

## Gotchas

- **Don't route with an LLM.** Using a frontier model as the router adds a $0.01-0.05 overhead to every single call. The router itself becomes the most expensive part of the pipeline. Use rules, classifiers, or a small fine-tuned model.
- **Don't skip context hygiene after the initial build.** Most cost blow-ups come from context window growth over time — conversation history accumulates, embeddings are re-computed unnecessarily, and older agents don't get retrofitted with new token budgets. Audit context size quarterly, not just on launch.
- **Budget caps without alerting are incomplete.** A hard cap that silently degrades model quality is a customer experience bug. Route budget-exhausted agents to a human handoff or a "try again later" state rather than a degraded model that produces wrong answers cheaply.
