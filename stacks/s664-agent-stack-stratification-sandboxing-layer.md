# S-664 · Agent Stack Stratification: Why Sandboxing Demands Its Own Infrastructure Layer

[You have a working agent that calls tools. It demos well. Then it lands in production, an agent reads a prompt-injected README, runs `curl` to exfiltrate env vars, and your vector DB credentials are in a pastebin. The reflex is to add more prompt hygiene. The real answer is architectural: sandboxing is its own infrastructure layer, and it needs to be treated as one.]

## Forces

- **The stack is stratifying whether you plan for it or not.** As agents move from demos to production, distinct layers emerge — orchestration, model serving, tool registry, retrieval, and sandboxing each have different defensibility profiles. Teams that try to be monolithic across all layers end up with a single point of compromise.
- **Standard cloud services weren't designed for agent execution patterns.** Lambda and Cloud Run reset between invocations, lack persistent filesystem state, and have no SDK-level sandbox lifecycle management. Agents that write and run code need something different.
- **Prompt injection is not a prompt problem.** It's an architecture problem. Hygiene at the prompt layer is necessary but insufficient — you need defense-in-depth that includes process isolation, VM boundaries, and egress controls.
- **Sandboxing is often the last thing teams design and the first thing that bites them.** The "tutorial cliff" — where a demo agent works but production fails silently — frequently manifests as a sandboxing failure, not a model failure.

## The move

Treat sandboxing as a first-class infrastructure layer with its own design principles:

- **Use Firecracker-based microVMs for agent code execution.** Firecracker (AWS's open-source VMM) provides hardware-level isolation with sub-100ms cold starts. Wrappers like E2B, Daytona, and Modal expose this as a developer API. This is categorically different from Docker — Docker containers share a kernel and can escape.
- **Enforce the five-layer defense stack.** Process isolation (minimal privileges, CPU/time limits) → VM/container isolation (microVMs) → system call filtering (block `execve`, `socket`) → runtime monitoring (kill anomalous processes) → human-in-the-loop (confirm on sensitive actions like deletions, refunds).
- **Design for persistent filesystem state across tool calls.** Agents need a filesystem that persists across multi-step tool invocations within a session. Lambda-style ephemeral execution breaks agent workflows.
- **Control network egress at the sandbox boundary.** Compromised sandboxes should not be able to call home, exfiltrate data, or reach internal services. Whitelist egress destinations.
- **Instrument sandbox lifecycle programmatically.** Create, pause, snapshot, and destroy sandboxes via SDK. You need this for scaling, cost management, and incident response.
- **Start with the most restrictive sandbox that doesn't break your use case.** Teams often start too permissive and harden retroactively — which means they harden after an incident.

## Evidence

- **HN discussion:** The agent stack is splitting into specialized layers; sandboxing is clearly becoming its own thing with Shuru, E2B, Modal, and Firecracker wrappers. Going monolithic across all layers is the wrong call because each has different defensibility profiles. — [Hacker News, phil dubach, 2026](https://news.ycombinator.com/item?id=47114201)
- **Competitive analysis:** Lambda and Cloud Run fall short for agent execution because they lack persistent filesystem state, sub-200ms cold starts, SDK-level sandbox lifecycle management, network egress controls, and horizontal scale to thousands of concurrent sandboxes. Four approaches compete: E2B (Firecracker microVMs, developer-focused), Daytona (agent runtime repositioned), Modal (Python-native serverless), Fly Machines (raw low-level primitive for custom builds). — [AgentMarketCap, April 2026](https://agentmarketcap.ai/blog/2026/04/07/ai-agent-sandbox-infrastructure-e2b-modal-daytona-fly-machines-secure-code-execution)
- **Threat model:** Attack vectors include prompt injection (malicious websites tricking agents into exfiltrating data), remote code execution (library vulnerabilities enabling privilege escalation), and denial of service (agents generating fork bombs or infinite loops). Defense requires all five layers — process isolation, VM/container isolation, system call filtering, runtime monitoring, and human-in-the-loop. — [vietanh.dev, February 2026](https://www.vietanh.dev/blog/2026-02-02-agent-sandboxes)

## Gotchas

- **"Docker is fine for agents" is false.** Docker containers share a kernel with the host; container escapes are documented, well-understood, and exploitable. If your agent runs untrusted code, you need hardware-level isolation. Firecracker microVMs are the minimum.
- **Cold start latency kills agent UX.** If your sandbox takes 3 seconds to spin up, your agent will appear unresponsive. Target sub-200ms. E2B and Modal optimize for this; custom Firecracker setups often don't.
- **Sandbox state bleeds if you don't design for cleanup.** Persistent sandboxes accumulate state that can affect subsequent runs. Snapshot-and-restore lifecycle management is required, not optional.
- **Egress controls are often an afterthought.** Teams add them after a sandbox reaches an exfiltration API. Design the egress policy before the agent hits production.
- **Human-in-the-loop gates create UX friction but are non-negotiable for sensitive operations.** "Always confirm before deletion" should be a default policy, not a feature you add when you get burned.
