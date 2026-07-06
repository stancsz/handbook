# S-460 · Agent Code Execution: Sandboxing as a First-Class Infrastructure Layer

When your agent writes and runs code, it becomes a process on your infrastructure — with all the access that implies. The sandboxing layer sits between "agent decides to execute" and "the command actually runs," and it is rapidly becoming its own distinct engineering discipline, separate from orchestration, separate from the model layer, and carrying real security and cost implications that teams discover the hard way.

## Forces

- **Agents that execute code cannot be reasoned about without execution isolation.** An agent with file system access, internet access, and a shell is not a language model — it is an untrusted process. Treating it as the former leads to incidents.
- **The execution layer is stratifying independently from orchestration.** HN discussion in early 2026 identified E2B, Modal, Firecracker wrappers, and Shuru as distinct players serving different isolation profiles — a signal that this problem space has enough specialization to warrant its own category. (Philipp Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying," Feb 2026 — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Naive Docker is insufficient for agent workloads.** Containers share the host kernel, making container escape a real risk for agents with elevated privileges. Agent-specific sandboxes need per-request resource limits, network egress controls, filesystem snapshots, and execution timeouts that Docker Compose doesn't provide out of the box. (Kubiya.ai, "AI Agent Deployment: Frameworks & Best Practices 2025" — https://www.kubiya.ai/blog/ai-agent-deployment)
- **Cold start latency kills agent UX.** Modal and similar serverless execution platforms advertise fast cold starts, but agent workloads that spin up on-demand Python interpreters, install dependencies, and initialize toolchains routinely hit 5–30 second cold starts — destroying the responsiveness that makes agentic interactions feel autonomous.
- **Code execution is the highest-risk tool in the agent's arsenal.** A single malformed or adversarial code generation pass, combined with insufficient sandboxing, can exfiltrate memory, pivot to internal services, or mine cryptocurrency on your infrastructure. The blast radius is not bounded by the agent's visible output.

## The Move

**Treat the execution environment as a typed interface, not an implementation detail.**

- **Isolate at the process level, not the container level.** Use microVM technology (Firecracker, gVisor) for agents that need kernel-level isolation. E2B provides cloud-hosted ephemeral sandboxes purpose-built for AI agent code execution — agents get a clean VM per task, destroyed after completion. (HN, "Local-First Linux MicroVMs for macOS" thread, Apr 2026 — https://news.ycombinator.com/item?id=47114201)
- **Define execution policies as code, not convention.** Specify which directories an agent can read/write, which network hosts it can reach, which environment variables it inherits, and which binaries it can execute — as structured policy, not "we'll monitor this." Tools like Open Policy Agent (OPA) or Cedar policies let you express these constraints declaratively.
- **Implement execution circuit breakers.** Hard timeout on any single execution step (30–120s), a maximum execution depth (no recursive subprocess spawning), a deny-list of dangerous binaries (`curl`, `wget`, `ssh` unless explicitly allowed), and a maximum output size before truncation.
- **Separate build-time and run-time environments.** Agents that need to run Python should not have `pip install` in the allowed execution path. Pre-install required packages in a read-only environment layer. Any runtime dependency installation should require an explicit approval workflow, not an autonomous agent decision.
- **Instrument execution observability with structured traces.** Log every execution: command, user, working directory, duration, exit code, stdout/stderr size, and network connections attempted. This is not optional — it is the only way to reconstruct what an agent did when something goes wrong. Langfuse and Phoenix both support tracing code execution events alongside LLM calls, enabling unified debugging. (LangSmith vs Langfuse vs Phoenix comparison, fp8.co — https://fp8.co/articles/LangSmith-vs-Langfuse-vs-Phoenix-LLM-Agent-Observability)
- **Pre-warm execution environments.** For latency-sensitive agent workflows, keep a pool of warm execution sandboxes idle — pre-initialized Python environments with dependencies loaded. Modal and AWS Lambda provide this natively; for self-hosted Firecracker, maintain a pool of pre-warmed snapshots.

## Evidence

- **Engineering blog (Dubach, Feb 2026):** The agent stack is splitting into specialized layers and sandboxing is "clearly becoming its own thing." E2B, Modal, Firecracker wrappers, and Shuru identified as distinct players at the execution isolation layer. — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **HN thread (Apr 2026):** Practitioners confirming the stratification — "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing." Multiple commenters citing direct experience with partial-AI software development and the need for execution isolation. — https://news.ycombinator.com/item?id=47114201
- **Deployment guide (Kubiya.ai, 2025):** Recommended Docker-based deployment for agents with caveats about enterprise requirements — authentication, permissions, audit trails — signaling that naive containerization is a starting point, not a production-ready solution. — https://www.kubiya.ai/blog/ai-agent-deployment
- **Observability comparison (fp8.co, 2026):** Phoenix and Langfuse both trace code execution events as first-class spans in agent traces, indicating that the execution layer is now explicitly modeled in agent observability pipelines. — https://fp8.co/articles/LangSmith-vs-Langfuse-vs-Phoenix-LLM-Agent-Observability

## Gotchas

- **Assuming Docker is "secure enough."** Container escape is not theoretical. An agent with write access to `/proc` or elevated capabilities inside a container can break isolation. If your threat model includes a misbehaving or prompt-injected agent, containers are not sufficient.
- **No execution policy until after an incident.** The right time to define what an agent can run is before it runs anything. Retrofitting execution policies around an existing agent is painful and creates gaps.
- **Silent execution failures.** An agent that fails to execute a code block often fails silently in the LLM's response — the model describes what it would have done without running it. You need execution telemetry, not just LLM trace data, to detect this pattern.
- **Cold start cost underestimation.** Serverless execution platforms charge for cold starts and have rate limits. A burst of concurrent agent requests can trigger throttling that manifests as intermittent failures — difficult to debug without execution layer metrics.
