# F-06 · Agent Sandboxing

Isolating the code an agent generates and runs, so a bad command — or an injected one — can't reach your real environment.

## Forces
- Agents now write and execute code you never reviewed; the blast radius is whatever the process can touch
- A standard Docker container shares the host kernel — not enough isolation against AI-generated code or indirect prompt injection
- Stronger isolation costs startup latency and money; weaker isolation costs you the host
- Cold-start tax per tool call makes a secure sandbox unusable if it's slow to resume

## The move

Pick the isolation tier by how much you trust the code, then layer defenses around it.

- **Match tier to trust.** microVMs (Firecracker, Kata Containers — dedicated kernel per workload) for unreviewed agent code; gVisor (user-space kernel, syscall interception, no full VM) for moderate trust; hardened containers only for vetted code. Plain Docker shares the host kernel — treat it as no boundary against injection.
- **Defense in depth.** The sandbox alone is not the control. Stack it: isolation boundary + resource limits + network egress controls + permission scoping + runtime monitoring. See [F-04](f04-guardrails.md).
- **Treat the sandbox as the agent's host.** Coding agents (Claude Code, Codex, OpenCode) are designed to run *inside* a sandbox, not alongside your real, unprotected environment.
- **Demand warm resume.** Standby sandboxes that restore filesystem + memory in ~25ms let the agent hold state across tool calls without paying cold-start latency every turn.
- **Map providers to tiers when buying.** E2B and Blaxel run Firecracker microVMs; Modal runs gVisor; Northflank runs Kata + gVisor with bring-your-own-cloud. Pick by isolation strength, session limits, and resume speed.

This is the execution-layer answer to the supply-chain and goal-hijacking failure modes in [F-05](f05-agent-failure-taxonomy.md): even a compromised agent is contained.

## Receipt
> Sourced from provider documentation (Modal, Northflank, E2B, Blaxel) and the OpenAI Agents SDK sandbox update ([Help Net Security, 2026-04-16](https://www.helpnetsecurity.com/2026/04/16/openai-agents-sdk-harness-and-sandbox-update/)). Isolation-tier taxonomy (microVM / gVisor / container) is the consensus framing across these sources. The ~25ms warm-resume figure is a vendor claim — benchmark against your own workload before relying on it. Verified 2026-06-25; not independently load-tested.

## See also
[F-04](f04-guardrails.md) · [F-05](f05-agent-failure-taxonomy.md) · [S-10](../stacks/s10-mcp.md) · [S-03](../stacks/s03-tool-use.md) · [W-02](../workspace/w02-claude-code.md)

## Go deeper
Keywords: `Firecracker` · `gVisor` · `Kata Containers` · `microVM` · `E2B` · `Modal sandbox` · `Northflank` · `indirect prompt injection` · `code execution sandbox`
