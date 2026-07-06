# S-223 · Agent Sandboxing and Code Execution Isolation

You shipped a coding agent. It works in demos. Then someone asks it to analyze a PDF or run a script from user input — and now it has shell access to your infrastructure. The moment an agent executes code you didn't review, you need isolation. Not as a best practice — as a hard requirement. Docker containers won't save you.

## Forces

- AI agents generate and execute code no human has reviewed — a single prompt injection can turn a coding assistant into a pivot point for attackers
- Docker containers explicitly share the host kernel and are not a security boundary for untrusted code — a kernel exploit gives root on the host
- The blast radius of a compromised agent is proportional to what it can reach: credentials, network, data, other services
- Sandboxing adds latency, cost, and complexity — but the alternative is unbounded risk
- The choice between MicroVMs, gVisor, WASM, and cloud-sandbox services has fundamentally different operational and security profiles

## The move

### 1. Never use Docker as a security boundary for agent-generated code
Docker containers are process isolation, not hardware isolation. They share the host kernel — container escape is a known attack class. Trend Micro demonstrated real exploitation: a malicious Excel file uploaded to a ChatGPT-style interpreter injected a persistent background process, scanned `/mnt/data` for documents, and replaced hyperlinks with phishing URLs. OpenAI patched the specific flaw (December 2024), but the class of vulnerability remains.

### 2. Use Firecracker microVMs for production code execution
Firecracker (AWS's open-source VMM, used by AWS Lambda and Fargate) provides hardware-virtualized microVMs that boot in ~125ms with <5MB overhead. Each agent session gets its own microVM with its own kernel. MicroVM-level isolation means a kernel exploit in one guest cannot reach another guest or the host.

- **E2B** packages Firecracker as a managed cloud service with SDKs for Python/JS, sandbox pooling for warm starts, and filesystem/network restrictions baked in
- **Daytona** offers self-hosted Firecracker with GPU passthrough support for ML workloads
- Rolling your own: the Firecracker Go SDK lets you provision per-session VMs with snapshot-restore for sub-second warm starts

### 3. Add gVisor as a lightweight alternative for lower-risk workloads
gVisor implements a user-space kernel (runsc) that intercepts system calls from the container. It provides stronger isolation than plain Docker without the VM overhead. Best for agents that need filesystem access but not full network access. Not appropriate for workloads requiring kernel fidelity.

### 4. WASM for language-agnostic, auditable sandboxing
WebAssembly runtimes (Wasmtime, WasmEdge) run untrusted code in a constrained environment with no direct OS access. Particularly useful for agents that need to execute code in multiple languages — WASM is language-agnostic and auditable. Performance is still catching up to native execution for compute-heavy tasks.

### 5. Apply least-agency principles at the sandbox level
The OWASP Agentic Top 10 recommends "least-agency": agents should receive the minimum permissions needed for the current task. Map this to sandbox design:
- No network access unless the task explicitly requires web scraping or API calls
- Read-only filesystem by default; grant write access to specific temp directories only
- Resource limits (CPU time, memory, max processes) as hard caps — agents cannot override these
- Network proxy with domain allowlisting for tasks that need web access

### 6. Anthropic's bubblewrap + Seatbelt pattern as a reference architecture
Anthropic's Claude Code uses bubblewrap on Linux and Apple's Seatbelt on macOS for filesystem isolation, plus a network proxy for domain restrictions. Result: 84% fewer permission prompts in internal usage because the sandbox enforces security boundaries instead of asking the user to approve each action. This is the model: let the infrastructure enforce constraints, not the user.

## Evidence

- **Engineering blog:** Anthropic's Claude Code sandboxing combines bubblewrap (Linux) and Seatbelt (macOS) for filesystem isolation, plus a network proxy for domain restrictions — resulting in 84% fewer permission prompts — [Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-sandboxing)
- **Security research:** Trend Micro documented container escape vulnerabilities in AI coding tool interpreters where malicious uploaded files led to persistent processes, document scanning, and phishing URL injection — [Paperclipped.de](https://www.paperclipped.de/en/blog/ai-agent-sandboxing-code-execution)
- **Comparative analysis:** E2B, Modal, and Docker sandboxing compared — E2B and Modal provide Firecracker-backed isolation; Docker is explicitly not a security boundary for untrusted code — [Kindatechnical](https://kindatechnical.com/agentic-ai/sandboxed-code-execution-e2b-modal-and-docker.html)
- **Community signal:** HN thread on agent stack stratification explicitly calls out sandboxing as a separate specialized layer alongside orchestration and memory, with E2B, Modal, and custom Firecracker wrappers as the emerging players — [Hacker News](https://news.ycombinator.com/item?id=47114201)
- **Architecture guide:** Sandboxed code execution pipeline for agents using Firecracker microVMs with snapshot-restore for warm pool management, including GPU passthrough for ML workloads — [Spheron Blog](https://www.spheron.network/blog/ai-agent-code-execution-sandbox-e2b-daytona-firecracker)

## Gotchas

- **Sandbox warm-up latency** — cold Firecracker microVMs boot in ~125ms; build a warm pool of pre-booted instances (4-8 always warm) to keep agent response times under 500ms
- **State persistence** — microVMs are ephemeral by design; if the agent needs to return to prior work, serialize state to an external store (Redis, S3) and restore on the next session
- **GPU access in sandboxes** — requires VFIO or MIG passthrough; native Firecracker doesn't support GPU, but Daytona and custom setups can do it with IOMMU-enabled passthrough — check your cloud provider's capabilities
- **gVisor breaks syscalls** — some Python packages with C extensions or unusual syscall requirements won't work under gVisor's user-space kernel; test your toolchain before committing to this approach
- **Least-agency is a design discipline, not a checkbox** — restricting network access sounds simple until your agent needs to call an external API. Plan allowlisting as part of the task definition, not as a post-hoc security measure
