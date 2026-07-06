# S-390 · MCP Security — The Command Injection Surface in AI Tool Calling

The Model Context Protocol connects agents to tools at scale — and its design assumes servers are trusted. That assumption is breaking in production. Command injection flaws appear in 43% of MCP servers, and the protocol's own SDK makes naive shell integration dangerously easy.

## Forces

- **MCP's M+N promise creates an M×N attack surface.** Every server is a potential pivot point. A vulnerable server doesn't just expose its own data — it gives the agent a foot into the host system
- **SDK ergonomics push developers toward unsafe patterns.** The stdio transport and Python decorators make it trivial to expose shell commands without input sanitization
- **Agents are user-authorized to act.** Unlike a web app where user input is sandboxed, an agent calling a compromised MCP server is already operating at elevated trust
- **Security tools haven't caught up.** Standard SAST, dependency scanning, and runtime protection were built for human-facing APIs, not agent-to-tool RPC

## The move

**Validate and sandbox every argument that flows into a system call.**

- **Input allowlisting over blocklisting.** Define what values each parameter *can* accept, not what it can't. For a filename parameter: `[a-zA-Z0-9._-]+` only
- **Principle of least privilege on the server side.** MCP servers should run with minimal OS permissions — no shell access, no sudo, no network unless required
- **Isolate stdio servers.** Local MCP servers running as the same user as the agent have full filesystem access. Consider subprocess sandboxing (landlock, seccomp) or dedicated service accounts
- **Inspect MCP server source before trusting it.** The OWASP AI-Injection landscape applies: prompt injection and tool-schedule misalignment are upstream risks that compound through MCP
- **Use transport-level security.** Prefer HTTPS/SSE over stdio for servers that need network access; stdio with a compromised parent process is game over

## Evidence

- **Research:** 43% of MCP servers have command injection flaws; exploit probability exceeds 92% when an agent uses 10 plugins simultaneously — [Deepak Gupta Research: MCP Enterprise Adoption Guide 2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025) (December 2025)
- **Security advisory:** OX Security published a full RCE vulnerability advisory (April 15, 2026) affecting 200,000+ MCP servers; 14 CVEs assigned to the MCP ecosystem. The root cause is not a library bug — it's the SDK's design pattern of encouraging direct shell invocation — [OX Security: MCP Supply Chain Advisory](https://www.ox.security/blog/mcp-supply-chain-advisory-rce-vulnerabilities-across-the-ai-ecosystem/)
- **Enterprise data:** Despite risks, MCP adoption is accelerating: 97M+ monthly SDK downloads, 5,800+ public servers, 300+ client applications, projected market growth from $1.2B to $4.5B. Organizations report 30% development overhead reduction and 50–75% time savings on common tasks — [Ragwalla: MCP Enterprise Adoption Report 2025](https://ragwalla.com/blog/mcp-enterprise-adoption-report-2025-challenges-best-practices-roi-analysis)

## Gotchas

- **Don't assume a server is trusted just because it comes from a reputable vendor.** Even Anthropic's own SDK examples are vulnerable if copy-pasted without sanitization. The vulnerability is in the pattern, not the package
- **Allowlist mismatches are subtle.** A regex like `[a-zA-Z0-9 ]+` still allows spaces that could become argument separators in some shell contexts — test with adversarial inputs: `backup.tar; rm -rf / ;`
- **MCP servers can call other MCP servers.** A compromised server can act as an agent and pivot to other servers in the environment — treat third-party servers as untrusted network peers
- **Audit your existing servers before adding new ones.** Security debt accumulates: the first 3 servers may be clean, but the 11th with a glob pattern in a filename parameter is the breach vector
