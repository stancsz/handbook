# S-602 · The MCP Trust Surface Is Unbounded Until You Sandbox It

MCP standardizes how agents discover and call tools. It solved the tool-integration sprawl problem — then created a bigger one: every MCP server is a trust boundary, and teams treat them like internal modules. With 5,800+ MCP servers and 10,000+ published, the blast radius of a compromised or buggy server is the entire agentic system.

## Forces

- **MCP grew from 100 servers to 5,800+ in 18 months.** The ecosystem moved faster than security thinking. Adoption incentives favor breadth; there's no equivalent pressure to audit tool servers.
- **43% of published MCP servers have command injection flaws.** A single malicious or buggy server in a chain of 10 has >92% probability of successful lateral exploit. The compounding is invisible because teams don't model trust boundaries between tools.
- **Auto-discovery collapses trust assumptions.** MCP's strength — agents automatically finding and using available tools — directly undermines manual security review. You cannot audit 10,000 servers.
- **Tool permissions cascade silently.** A file-system MCP server with read/write access used by a research agent is a different risk posture than the same server used by a code-execution agent. Teams conflate the server's access with the use-case's access.

## The move

Sandbox every MCP server at the infrastructure layer, regardless of perceived trust:

- **Isolate each server in its own sandboxed process or container** (Firecracker microVMs, E2B, Modal, Shuru, or equivalent). E2B and Modal specifically built for agent sandboxing workloads.
- **Scope permissions to the minimum required** — not "read/write filesystem" but "read only `/tmp/workspace/` for 30 minutes." Apply time-boxes and resource limits.
- **Validate tool outputs at the agent boundary**, not just inputs. An MCP server returning corrupted or malicious data to an agent that acts on it is equally dangerous.
- **Use typed schemas at every tool boundary** — MCP tool calls should have structured output schemas the agent cannot silently overflow or inject through.
- **Monitor tool-call provenance** — track which MCP server produced which data flowing into which agent decision. If you can't replay it, you can't audit it.
- **Audit MCP server provenance before adding to production**, even trusted ones. Check dependency trees, review permissions requested vs. permissions needed.

## Evidence

- **Blog post:** 43% of published MCP servers have command injection flaws; exploit probability exceeds 92% with 10 plugins — [guptadeepak.com, Dec 2025](https://guptadeepak.com/the-complete-guide-to-model-context-protocol-mcp-enterprise-adoption-market-trends-and-implementation-strategies)
- **HN discussion:** "Sandboxing is clearly becoming its own thing" — E2B, Modal, Firecracker wrappers emerge as distinct layer in agent stack — [HN, Jun 2025](https://news.ycombinator.com/item?id=47114201)
- **GitHub README:** Framework decision guide explicitly calls out MCP integration as a primary evaluation dimension for production agent stacks — [benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)

## Gotchas

- **"It's an internal MCP server, it's fine"** — internal servers have the same vulnerability surface as external ones. The threat model is the code, not the network.
- **Trusting the MCP server's self-reported permissions** — servers can request more permissions than they need; agent tool-selection logic may grant all requested permissions by default.
- **Forgetting that agent reasoning chains amplify a single bad tool result** — a corrupted output from one MCP server propagates through every downstream agent that acted on it.
- **Treating MCP security as a one-time setup** — MCP server count grows over time; security posture must be continuously audited as new tools are added.
