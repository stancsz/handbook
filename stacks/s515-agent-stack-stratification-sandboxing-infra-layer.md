# S-515 · Agent Stack Stratification: Sandboxing as Its Own Infrastructure Layer

When code execution moved from "the agent runs it on the host" to "the agent runs it in a sandbox," that seam became a new layer — and it's not ops, it's architecture. The evidence from 2025-2026 production deployments is clear: teams that treat sandboxing as a checkbox hit incidents; teams that treat it as a first-class infrastructure layer build reliably.

## Forces

- **"IDEsaster" made the risk concrete.** In December 2025, a security researcher disclosed 30+ vulnerabilities across Cursor, Windsurf, GitHub Copilot, Cline, and other AI-powered IDEs — all sharing the same root cause: agents executing code with the permissions of the local user, inside shared process environments, with no isolation boundary. The name stuck.
- **Context degrades in the middle.** Long context windows are a trap, not a solution. Research shows model performance on reasoning tasks degrades by as much as 73% when critical information gets buried in the middle. Single-agent "God Prompt" architectures hit this wall consistently.
- **The stack is stratifying, not converging.** 37% of enterprises already run 5+ AI models in production. The agent stack is splitting into specialized layers — Context, Orchestration, Memory, Tooling, Sandboxing, Serving — each with different defensibility profiles and different rebuild difficulty. Treating it as a monolith means owning the worst tradeoff at every layer.
- **Cold start vs. state persistence is a real product decision.** Sub-200ms vs. 25ms resume isn't an ops metric — it's a UX and architecture decision that changes how agents are designed.
- **40% of enterprise agentic AI projects will be canceled by end of 2027** (Gartner), partly because teams underestimate infrastructure complexity including sandboxing.

## The Move

Treat sandboxing as a distinct architectural layer with its own tradeoff surface. Key decisions:

- **Pick your isolation primitive by blast radius need, not by default.** Firecracker microVMs (E2B) give per-sandbox kernel isolation with sub-200ms cold starts via pre-warmed pools — best for code-interpreter flows and data-analysis agents where speed dominates. Daytona (open-source) pivoted from dev-environments to agent sandboxes in 2025 and now owns the self-hosted/governance use case. Modal's persistent instances support sub-25ms resume for stateful coding agents that maintain loaded repository state across interactions.
- **Size the sandbox radius to the minimum viable surface.** The sandbox's job is to make the blast radius small, time-bounded, and auditable. A coding agent that needs filesystem access to a repo and nothing else should get exactly that — not a full container with network access.
- **Network should be default-closed.** E2B's model is HTTPS allowlists, default-closed. This isn't paranoid — it's the minimum viable surface for an agent that needs to call APIs.
- **State persistence is a first-class feature for coding agents.** If your agent clones a repo, installs dependencies, and does partial work before the user returns, you need filesystem snapshots that survive across sandbox runs — not just ephemeral execution.
- **Sandbox lifecycle management belongs in the orchestration layer, not the agent.** The agent should call `execute_code(task)` and get a result. The orchestration layer owns timeouts, retry policies, resource limits, and cost caps.
- **Combine sandboxing with plan-then-execute.** Sandboxing limits blast radius on execution; a semantic gate between planner and executor limits blast radius on intent. Both layers are necessary in production.
- **Track cost per sandbox-second, not per-call.** E2B charges per second of sandbox time. Long-running sandbox sessions have a fundamentally different cost profile than stateless API calls. Model this explicitly.

## Evidence

- **Blog post / Security research:** "IDEsaster" — 30+ vulnerabilities disclosed across Cursor, Windsurf, GitHub Copilot, Cline, and others in December 2025, all caused by agents executing code with local user permissions and no isolation boundary — [Agent MarketCap](https://agentmarketcap.ai/blog/2026/04/11/code-execution-sandbox-race-2026)
- **HN discussion + engineering blog:** The agent stack splitting into specialized layers with sandboxing as its own defensibility layer; Gartner data (40% project cancellation by end 2027, 37% of enterprises with 5+ models in production) — [HN #47114201](https://news.ycombinator.com/item?id=47114201) + [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Benchmarking article:** E2B (Firecracker microVMs, sub-200ms cold start, per-second pricing), Daytona (open-source, self-hosted, governance-first), Modal (persistent instances, 25ms resume for stateful agents) — [CallSphere AI](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)
- **Decision matrix:** Side-by-side comparison of Docker, E2B, Modal, Firecracker, gVisor, and Kata Containers for agent code execution across latency, security, and ops cost — [AgentList](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice)
- **Framework comparison:** LangGraph (FSM/node+edge model, ~30K stars, best for complex graph traversal), CrewAI (role/goal/backstory model, fast onboarding, ~70% of use cases without branching), AutoGen v0.4+ (async group chat model) — [hjLabs.in](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Production metrics:** Multi-agent production failures attributed to state management, credential governance, and observability gaps — not model quality — [TrueFoundry](https://www.truefoundry.com/blog/multi-agent-architecture)
- **Observability requirements:** Minimum stack tracks per-span latency, token counts, cost, retrieval similarity scores, and automated quality evaluation across agent boundaries — [aliac.eu](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **Docker containers are not sandboxes.** They share the host kernel. For agents executing untrusted code, use Firecracker microVMs or gVisor/Kata Containers for proper isolation. Docker is fine for agent infrastructure isolation, not code execution isolation.
- **Persistent sandbox state is a security surface.** If your sandbox maintains filesystem state across runs, that state is an attack vector. Design snapshot restore and state teardown explicitly.
- **Cold start optimization is a trap if it changes your error model.** Sub-200ms is great until the agent makes 1,000 cold-start calls in a loop because there's no retry/backoff discipline around warm pool exhaustion.
- **Framework choice is load-bearing for architecture.** LangGraph's FSM model makes branching explicit and testable. CrewAI's team model is cleaner for linear workflows but requires meta-orchestration for complex graphs. Mixing models mid-stack creates conceptual debt that's hard to pay down.
- **Observability across agent boundaries is the hardest part.** LangSmith, Arize Phoenix, and Langfuse each handle multi-agent traces differently. Pick before you scale — retrofitting traces across a growing agent graph is painful.
