# S-253 · Agent Sandboxing: The Layer Nobody Designed For

Your agent can write and execute code, call APIs, and mutate state. It is running inside the same process boundary as everything else. This was fine in demos.

## Forces

- **Agents execute untrusted code — but most teams don't isolate them.** Standard Docker/runc containers share the host kernel and can escape via syscall vulnerabilities. The agents making real decisions in production are often running in the least isolated environment on the team.
- **Sandboxing keeps being rebuilt from scratch.** Every team that adds code execution hits the same isolation problem and solves it ad hoc. The pattern is mature in theory (Firecracker, gVisor, MicroVM tech has existed since 2018-2020) but poorly codified for agent developers specifically.
- **Sandbox overhead vs. agent latency is a real trade-off.** Sub-200ms startup for ephemeral VMs is achievable, but the operational complexity is non-trivial. Teams either over-engineer or under-engineer — there's no standard middle path for agent workloads.

## The move

Design the execution layer as a first-class architectural concern, not an afterthought.

- **Use Firecracker microVMs (Layer 1) for hard multi-tenant isolation.** Hardware-level VMs with dedicated kernels. Each agent (or agent group) gets its own microVM. This is what E2B, Manus, and Manus-like platforms run on internally. Firecracker was open-sourced by AWS in 2018 and is battle-tested at scale.
- **Use embeddable runtimes (Layer 2 — E2B, microsandbox) for fast API-level integration.** If you need code interpreter capabilities in days not months, E2B's SDK wraps Firecracker complexity behind a clean interface. `microsandbox` (open-source, self-hosted) uses libkrun for library-based KVM virtualization with sub-200ms cold starts — no SaaS dependency, no data leaving your network.
- **Use managed platforms (Layer 3 — Modal, Daytona, Northflank) when you need GPUs, persistent volumes, or fleet management.** Northflank claims 100,000+ concurrent sandbox environments. Modal handles ephemeral compute with Python-first ergonomics.
- **Map isolation level to trust level.** Untrusted external code → microVM (Level 3-4). Semi-trusted internal tools → gVisor or LiteXL (Level 2). Trusted agent code → namespaced containers (Level 1). Defaulting everything to the same level wastes resources or invites risk.
- **Combine with MCP for tool security boundaries.** MCP defines *what* tools an agent can call. Sandboxing defines *what happens when* it calls them. Both are needed; neither is sufficient alone.
- **Self-host when data residency matters.** The moment agent inputs touch customer data, a cloud sandbox SaaS may create compliance exposure. microsandbox and self-deployed Firecracker are the available self-hosted options.

## Evidence

- **HN discussion:** The agent stack is "splitting into specialized layers and sandboxing is clearly becoming its own thing." Firecracker wrappers (E2B, Modal, custom Shuru) are emerging as a distinct category from orchestration and LLM layers. — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Technical walkthrough:** Manus runs "millions of isolated agents" using E2B's Firecracker microVM infrastructure, enabling full OS access per agent without shared state risk. Each sandbox gets a dedicated kernel, hardware-level isolation. — [Undercode Testing](https://undercodetesting.com/scaling-ai-agents-with-secure-e2b-sandboxes-a-technical-breakdown/), June 2025
- **Comparative guide:** Three isolation layers now exist as a framework: Layer 1 (Firecracker/gVisor primitives), Layer 2 (E2B/microsandbox embeddable runtimes), Layer 3 (Modal/Daytona/Northflank managed platforms). Standard Docker/runc containers are Level 1 — insufficient for untrusted agent code. — [Substack: AI Agent Sandboxing Guide 2026](https://manveerc.substack.com/p/ai-agent-sandboxing-guide)
- **MCP + memory integration:** HPE Developer blog demonstrates Qdrant vector storage with MCP protocol as semantic memory for agents — Qdrant as the persistence layer, MCP as the tool interface, enabling agents to actively curate and query their own knowledge base across sessions. — [HPE Developer Portal](https://developer.hpe.com/blog/part-8-agentic-ai-and-qdrant-building-semantic-memory-with-mcp-protocol/)

## Gotchas

- **Firecracker's operational overhead is real.** You need TAP interfaces, root filesystems, and lifecycle management. Layer 2 SDKs exist precisely to hide this. Don't roll your own unless you have specific compliance or latency requirements that Layer 2 can't meet.
- **Cold start latency varies wildly by approach.** E2B claims ~500ms, microsandbox claims sub-200ms. If your agent is latency-sensitive, measure the sandbox layer end-to-end — it's often the dominant delay in agentic pipelines.
- **Sandbox + orchestration coupling is a design smell.** If your sandbox configuration is tightly coupled to your orchestrator, you can't swap orchestration frameworks. Keep the execution boundary clean so LangGraph ↔ CrewAI changes don't cascade into sandbox rewrites.
- **MCP servers are multiply-attacked surface area.** Every MCP tool you expose from behind a sandbox expands the blast radius. Treat MCP tool definitions like API contracts — version them, audit them, and validate inputs at the sandbox boundary.
