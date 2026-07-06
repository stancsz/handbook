# S-618 · Production Token Economics: What Actually Costs Money in Agentic Systems

Teams building agentic systems consistently budget wrong because they price LLM API calls like they price a chatbot. The math is different once agents loop: step count multiplies cost super-linearly, context repetition dominates, and the first runaway loop teaches you everything the hard way.

## Forces

- **Cost is a function of steps × model × context, not calls.** A single agent run with 8 steps costs 4x more than one with 2 steps, even with the same model. Teams underbudget by 2-5x because they estimate per-query, not per-task.
- **LLM API is 60–80% of total agent cost.** Infrastructure (vector DB, sandboxing, hosting) is noise compared to model spend. Cost optimization starts and ends with the token pipeline.
- **Context repetition is the hidden cost amplifier.** Repeated system prompts, tool schemas, and conversation history across multi-step runs can consume 40–60% of tokens without delivering value. [S-08](s08-prompt-caching.md) and [S-616](s616-agentic-plan-caching-the-50-cost-reduction-pattern.md) address this at the provider and agent level respectively.
- **Enterprise agent spend averages $85K/month but is 60–85% recoverable.** Teams that implement disciplined cost engineering — not smaller models — achieve 40–70% cost reduction without quality loss.

## The move

**Model choice × average step count = your cost floor. Everything else is optimizable.**

Production data from 4 systems tracked over 6 months (October 2025 – April 2026) shows this formula holds:

| System | Primary Model | Cost/Execution | Monthly Volume | Monthly API Cost |
|--------|---------------|----------------|----------------|------------------|
| A — Support Triage | GPT-4o-mini | $0.012 | 12,000 runs | $144 |
| B — Document Processor | Claude 3.5 Sonnet | $0.24 | 8,500 runs | $2,040 |
| C — Sales Research Crew (3 agents) | GPT-4o + Claude 3.5 | $0.51 | 3,200 runs | $1,632 |
| D — Code Review Agent | Claude 3.5 Sonnet | $0.38 | 5,800 runs | $2,204 |

**Key levers ranked by impact:**

1. **Step count reduction** — halving steps halves cost. Design agents for 2-4 tool calls per run; >6 steps should be a red flag.
2. **Model routing** — route simple tasks to fast/cheap models (GPT-4o-mini, Haiku). Use Claude 3.5/GPT-4o only for tasks that justify it. Tiered routing typically saves 30–50%.
3. **Prompt caching** — Anthropic's cached prompts and OpenAI's token-saving techniques eliminate repeated system-prompt overhead. For agentic systems with long system prompts and tool schemas, this alone recovers 15–25%.
4. **Context window budgeting** — aggressive truncation of conversation history and retrieved documents prevents token bloat. A naive RAG agent retrieving 10 documents at 2K tokens each adds 20K tokens/turn.
5. **Hard budget circuit breakers** — set per-session and per-day spend limits at the API key level. Runaway agent loops have cost teams anywhere from $15 in 10 minutes to $47,000 over eleven days.

## Evidence

- **Primary research (6-month production study):** 4 agentic AI deployments tracked October 2025 – April 2026. LLM API = 60–80% of total cost across all systems. Single-agent simple tasks: $0.012–$0.05/execution; multi-agent complex: $0.38–$0.51/execution. — [Inventiple: Agentic AI Production Cost: 6 Months of Real Data](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Enterprise benchmark:** Enterprises average $85,521/month in AI operational costs as of 2025. 60–85% of spend is recoverable through cost engineering. Runaway agent loop incidents cost teams $15 to $47,000 depending on duration. — [Zylos.ai: AI Agent Cost Engineering — Production Token Economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **SWE-bench realism:** Leading agent systems complete only 19.25% of dynamic SWE-bench tasks (vs. curated benchmark subsets). The performance gap is an architecture and cost problem: more capable models + fewer steps beats less capable models + more retries. — [Azumo: AI Agent Architecture Patterns — A Production Reference](https://azumo.com/artificial-intelligence/ai-insights/ai-agent-architecture)
- **Stack stratification:** Enterprise AI stack is decomposing into 6 layers with different cost profiles. Context layer (vector DB, retrieval) is highest lock-in; orchestration is medium defensibility; sandbox/execution is becoming a commodity. — [Philipp Dubach: Don't Go Monolithic; The Agent Stack Is Stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)

## Gotchas

- **Budgeting per-query is wrong.** Bill for the full task (all steps, all retries, all context). Teams that bill per API call underestimate by 3-5x.
- **Cheaper model + more steps can cost more.** Haiku at 12 steps often costs more than Sonnet at 3 steps. Model price and step count must be co-optimized.
- **Prompt caching at provider level ≠ semantic memory.** Anthropic/OpenAI caching helps with repeated system prompts; you still need semantic memory (episodic, procedural) to avoid re-explaining domain context on every run.
- **Sandbox and vector DB costs look small but scale.** Individual line items seem negligible; at 10K+ runs/month, vector DB hosting ($50-200/month) and sandbox compute ($100-500/month) become real budget items.
- **Multi-agent crews compound cost super-linearly.** A 3-agent crew where each agent calls the LLM 3 times = 9 LLM calls minimum. CrewAI users consistently report this as their biggest surprise on the first bill.
