# S-324 · Agent Sandboxing: The Layer Nobody Planned For (And Now Can't Ignore)

Every prototype agent runs as a Python process with filesystem access. Every production system eventually discovers that letting an agent run arbitrary code, browse the web, or call APIs without isolation is a liability. Sandboxing is not an afterthought — it is an architectural primitive that belongs in the stack from the start.

## Forces

- **Agents need to execute code, browse, and call tools — each of which is a blast radius.** A single tool call to `subprocess.run` or a browser with an XSS vulnerability gives an agent the equivalent of shell access. The blast radius scales with capability.
- **The agent stack is stratifying whether you plan for it or not.** By 2026, the monolithic "LangChain + Python script" prototype is giving way to specialized layers: orchestration (LangGraph, CrewAI), memory (vector DBs), tool execution (MCP servers), and sandboxing — each with different defensibility profiles and scaling characteristics.
- **Sandboxing vendors are emerging to fill a real gap.** E2B, Shuru, Modal, Firecracker wrappers — each approaches the isolation problem differently, and picking the wrong one is an expensive migration.
- **PostHog's lesson cuts both ways.** They found that building an MCP server to expose their product to agents was simpler and higher-leverage than building a custom agent. But an MCP server still needs execution context — sandboxing is where that context gets defined.

## The move

Treat sandboxing as a first-class infrastructure layer, not a security afterthought. Choose your isolation primitive based on the threat model:

- **MicroVM (Firecracker, gVisor):** Strongest isolation. Cold start ~100-300ms. Good for untrusted code execution, browser automation, internet browsing. Vendors: E2B, Shuru.
- **Container + seccomp/AppArmor:** Lighter than MicroVM, ~10-50ms overhead. Good for partially-trusted code with restricted syscalls. Native Docker/Kubernetes with security profiles.
- **Modal.com / serverless functions:** Code execution in managed, ephemeral environments. Best for trusted code with GPU/CPU burst needs. Not true security sandboxing but provides process-level isolation and autoscaling.
- **LangGraph + typed state + PostgreSQL checkpointing:** Does NOT sandbox on its own — adds durable state management and human-in-the-loop interrupts (pause/resume) to multi-agent graphs. Combine with a sandbox layer for the execution boundary.

Key implementation decisions:
- Never feed raw DOM to an agent — create abstract actions (e.g., "click 'Apply Now' button") so UI changes don't break agents.
- Keep sandboxed execution stateless; push all meaningful state to your persistence layer.
- Pair sandboxing with observability: every tool call in every sandbox should emit structured logs (input context, model reasoning, tool result, final output).

## Evidence

- **Hacker News (primary):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — commenter on Show HN thread discussing agent architecture stratification, June 2025 — https://news.ycombinator.com/item?id=47114201
- **PostHog engineering blog:** "The capabilities of agents are unquestionably valuable but this does not mean you need to build a custom one. Making your product accessible to agents is often a better option." — Ian Vanagas, PostHog, March 2026 — https://newsletter.posthog.com/p/what-we-wish-we-knew-before-building
- **Reddit (r/aiagents):** "The key is never feeding raw DOM to the agent. Instead, create abstract actions like 'click button Apply Now', so minor UI changes don't break your agents." — real production experience sharing browser automation patterns — https://www.reddit.com/r/aiagents/comments/1pb7ls9
- **Reddit (r/LocalLLaMA):** "Stability comes from combining Playwright (reliable) with a managed service like Browserbase that handles session/cookie persistence and recovery." — production web interaction stack — https://www.reddit.com/r/aiagents/comments/1pb7ls9

## Gotchas

- **Sandboxing ≠ observability.** You can have a well-sandboxed agent that is completely opaque inside. Log every LLM call, tool invocation, and state transition — debugging agent failures without this is like debugging distributed systems without logs.
- **Modal is not a security sandbox.** It provides excellent compute isolation and autoscaling for trusted code, but it does not provide the process-level isolation needed for untrusted code execution. Don't use it as a substitute for Firecracker/gVisor when the agent runs external code.
- **LangGraph's checkpointing handles state recovery, not blast radius.** Checkpoint + resume lets you survive pod restarts, but it does nothing to contain an agent that calls `rm -rf /`. Pair the state management layer with a sandboxing layer.
- **Cold start latency kills UX for interactive agents.** Firecracker VMs provide strong isolation but add 100-300ms per invocation. Profile the user-facing path and pre-warm sandboxes where the latency budget doesn't allow cold starts.
