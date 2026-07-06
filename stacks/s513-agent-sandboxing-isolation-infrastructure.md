# S-513 · Agent Sandboxing: Isolation as a First-Class Infrastructure Layer

When agents started running code, teams wrapped them in Docker. When that wasn't enough, they reached for VMs. Now a whole category of specialized products has crystallized around one idea: **the agent execution environment is its own design problem**, and it deserves its own layer in the stack.

## Forces

- **Code execution risk scales with autonomy** — the more an agent can do, the more catastrophic a compromised or misbehaving agent becomes. Docker containers share a kernel; a runaway agent with write access can escape.
- **Latency vs. isolation is a real trade-off** — Firecracker microVMs start in ~125ms; full VMs take minutes. Not every use case needs the same isolation level, but most teams default to too little.
- **Security and capability are in tension** — locked-down sandboxes can't browse the web, run terminal commands, or access secrets. Agents need *enough* access to be useful but *not so much* that they become a pivot point for attackers.
- **The stack is stratifying** — what was once "just run it in Docker" is now a layered decision: container per agent, microVM per agent, remote sandbox service, or managed cloud runtime. Each layer has different cost, latency, and security profiles.

## The move

Treat the agent execution environment as a separate infrastructure concern — one with its own procurement, configuration, and monitoring — not a line in a Dockerfile.

- **Default to Firecracker microVMs for code-writing agents.** Hardware virtualization gives kernel-level isolation Docker can't match. E2B, Daytona, and similar services expose this via managed APIs.
- **Pick isolation level by consequence, not consistency.** Network-accessible agents need microVMs. Read-only analysis agents can run in containers. Don't pay the cold-start latency tax for low-stakes tasks.
- **Route secrets through a proxy, never into sandbox memory.** Managed sandbox providers generally don't support runtime secret injection. Build a proxy layer so credentials never touch the sandbox's process space.
- **Limit egress at the sandbox boundary.** Static IPs, egress proxies, and allowlist-only outbound access prevent compromised agents from exfiltrating data or pivoting to internal services.
- **Monitor sandbox health as a first-class metric.** Track: sandbox spin-up latency, OOM rate, network packet drops, and per-sandbox cost. These reveal agent behavior problems faster than LLM-level logs.
- **Treat sandbox templates as code.** Freeze working sandbox configurations (OS image, installed tools, network rules) in version-controlled configs so agents behave consistently across environments.

## Evidence

- **HN thread (2025):** An HN commenter with production partial-AI software development experience noted: "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." A related post on the same thread argued that these layers have "very different defensibility profiles" and that going monolithic across them is the wrong call. — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **E2B / Manus case study (2025):** Manus uses E2B's sandbox technology to run "millions of isolated agents" on Firecracker microVMs, providing "full OS access without shared state risks." E2B's own product pages list use cases for deep research agents, AI data analysis, coding agents, vibe coding, reinforcement learning, and computer use — all requiring different isolation levels. — [E2B Docs](https://e2b.dev/), [Undercode Testing](https://undercodetesting.com/scaling-ai-agents-with-secure-e2b-sandboxes-a-technical-breakdown/)
- **CallSphere analysis (2026):** A technical breakdown comparing E2B, Daytona, and Modal for production agentic workloads. Key finding: in 2024 you could ship an agent that ran code in a Docker container. By 2025, "agents that write and run code need real isolation" became the baseline expectation. — [CallSphere Blog](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)

## Gotchas

- **Cold start latency ruins low-latency use cases.** Firecracker microVMs start in ~125ms, but orchestration overhead can push this to 1-3 seconds. Modal's ephemeral functions and E2B's prewarmed instances help, but you need to benchmark against your P99 target.
- **Managed sandbox egress is harder than it looks.** E2B requires self-hosted IP tunneling via a gateway VM. Daytona and Modal handle this differently. If you need static IPs or per-sandbox IP allowlisting, check the provider's egress model before committing.
- **Sandbox escape is still possible with Firecracker.** Firecracker has had CVEs (e.g., CVE-2025-2772). Treat it as a strong boundary, not an absolute one — combine with network-level segmentation and least-privilege IAM on the surrounding infrastructure.
- **You're now operating two products.** Every sandbox provider is a dependency. When E2B has an outage, your coding agent is down. Factor this into your SLOs and runbook.
