# S-669 · The Orchestration Framework Trap: Graphs vs. Roles vs. Conversations

[You need to coordinate multiple AI agents. Every framework promises the same thing — multi-agent orchestration — but LangGraph, CrewAI, and Microsoft Agent Framework encode completely different mental models. Pick the wrong one and you refactor in 6–12 months. Pick the safe choice and you might move too slowly. The decision is architectural, not technical.]

## Forces

- **Graph expressiveness vs. speed of iteration** — LangGraph's directed graphs with cyclical state give you precise control, but you write the flow explicitly. CrewAI gets you a working prototype in an afternoon, then you hit a ceiling.
- **Hierarchical vs. emergent coordination** — Should you define who talks to whom (LangGraph, CrewAI hierarchical), or put agents in a room and let them negotiate (Microsoft Agent Framework conversational)?
- **Vendor ecosystem lock-in** — Microsoft Agent Framework 1.0 GA (April 2026) unified AutoGen + Semantic Kernel. If you're in Azure, it's a natural fit. If you're not, it adds gravity you may not want.
- **The rewrite tax** — Teams that start with CrewAI for speed and migrate to LangGraph for control report 3–6 months of painful refactoring. The mental model shift is significant.
- **Parallel vs. sequential task structure** — Google Research (180 agent configurations evaluated) found multi-agent coordination dramatically improves performance on parallelizable tasks but *degrades* performance on sequential ones. Your workflow shape should drive the framework, not the other way around.

## The move

**Default to LangGraph unless you have a specific reason not to.** The learning curve is the investment; painful rewrites are the cost of the shortcut.

- **LangGraph** — Explicit directed graphs with cyclical state. You build the flowchart, the framework executes it. Best for complex, stateful, production-critical workflows where you need to inspect, replay, and reason about agent state at every step. Steeper upfront cost, lower long-term maintenance burden. [Gheware DevOps AI Blog — "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6–12 months in"](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **CrewAI** — Role-based team model: you define agents by role, goal, and backstory; assign tasks; the framework handles delegation. Fastest path to a working prototype. Ships with `agents.yaml`/`tasks.yaml` config and a visual CrewAI Studio (AMP). Hits ceiling on complex, non-hierarchical workflows within 6–12 months. GitHub: 54,242+ stars as of June 2026, 100,000+ certified developers. [Automation Atlas — CrewAI tool page](https://automationatlas.io/tools/crewai)
- **Microsoft Agent Framework 1.0** (ex-AutoGen, GA April 2026, unified with Semantic Kernel) — Conversational multi-agent with emergent coordination patterns. Best for Azure-native teams who want the ecosystem backing. `autogen_agentchat` v0.2 is now officially legacy. [TURION.AI — "Microsoft announced Agent Framework 1.0 GA on April 3, 2026, unifying AutoGen and Semantic Kernel into a single production SDK"](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)

When to actually use CrewAI instead: marketing/sales automation where agents map cleanly to distinct roles (strategist, creative, analyst) with well-defined handoffs. Opensoul's 6-agent marketing agency stack is a canonical example — director, strategist, creative, producer, growth marketer, analyst all with distinct mandates. [HN Show — Opensoul agentic marketing stack](https://news.ycombinator.com/item?id=47336615)

## Evidence

- **Orchestration comparison (primary research):** Three frameworks, three coordination philosophies. Turion tested all three in production systems and found the decision tree is: "Do you need explicit, inspectable state transitions? → LangGraph. Do your agents map to distinct roles with clear delegation? → CrewAI. Are you deep in Azure and want conversational emergence? → Microsoft Agent Framework." — [TURION.AI — LangGraph vs CrewAI vs AutoGen: 2026 Comparison](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Multi-agent scaling science (Google Research):** Through controlled evaluation of 180 agent configurations across four benchmarks (Finance-Agent, BrowseComp-Plus, PlanCraft, Workbench), Google Research found multi-agent architectures improve performance on parallelizable tasks but degrade on sequential ones. Introduced a predictive model identifying optimal architecture for 87% of unseen tasks. — [Google Research Blog — Towards a Science of Scaling Agent Systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work)
- **Expert recommendation on default choice:** "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6–12 months in." — [Gheware DevOps AI Blog — LangGraph vs CrewAI vs AutoGen Comparison](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Sequential tasks don't benefit from multi-agent** — Google Research empirically showed degradation, not improvement. If your workflow is a linear chain (retrieve → reason → respond), a single agent with a longer context window often beats splitting across agents.
- **CrewAI's "manager agent" in hierarchical mode is a black box** — When the auto-generated manager delegates, you can't easily inspect why it chose that agent for that task. Debugging is painful.
- **AutoGen v0.2 is legacy as of April 2026** — If you're reading older guides, the `autogen_agentchat` package is dead. Microsoft's new SDK has different APIs and a different model.
- **Role-based mental model creates hidden coupling** — CrewAI agents are tightly bound to their defined roles. When a task spans roles or requires improvisation, the framework fights you.
- **MCP adoption is changing tool-calling patterns across all frameworks** — All three now support Model Context Protocol. But MCP server quality varies widely; a bad MCP server can make even a well-architected agent system behave unpredictably.
