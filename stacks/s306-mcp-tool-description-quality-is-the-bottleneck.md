# S-306 · MCP Is the Standard — Now Tool Description Quality Is the Bottleneck

By 2026, MCP (Model Context Protocol) has won the tool-calling standardization race. Adoption is real: 9,652+ servers in the official registry, 15,926 GitHub repos tagged `mcp-server`, 97M+ monthly SDK downloads, and 41% of surveyed organizations in production (up from near-zero in late 2024). But the bottleneck has shifted. Once the transport layer standardizes, the differentiator is what you put into it — specifically, how you describe tools to the model.

## Forces

- **MCP solved the integration problem but not the quality problem.** The protocol handles transport, authentication, and schema delivery. It says nothing about whether your tool descriptions are actually useful to a model — that's an engineering decision you make.
- **Tool description quality is measurable and directly correlates with success.** Early MCP servers shipped with vague schemas (e.g., "search database" with no parameters). Teams that invested in precise parameter descriptions, error case documentation, and usage constraints saw dramatically lower failure rates.
- **89.8% of MCP tool descriptions have unstated limitations** — missing constraints on input formats, missing error responses, missing rate limits. The model fills those gaps with guesses, and guesses are hallucinations.
- **The "10K servers" number masks consolidation.** The MCP Institute found that while public MCP server repos grew from ~2,000 to 12,000+ YoY, most production usage concentrates on a small set of high-quality servers. Teams build custom servers for their domain, not generic ones.

## The move

**Invest in tool description authoring as a first-class engineering discipline.**

- Write tool descriptions at the level of a junior developer being handed a poorly-documented API: what does it do, what does it NOT do, what valid inputs look like, what failure modes exist
- Include `constraints` and `examples` in your schema, not just names and types — models respond significantly better to constrained descriptions
- Use a tool-description review step in your CI pipeline: run the tool description against a model and verify it calls the tool correctly on a test case before shipping
- For custom MCP servers, model them as independent services with explicit input/output contracts — don't expose raw database tables, expose intent-aligned operations
- Rate-limit every tool explicitly in the schema: a model that doesn't know a tool has a 10 req/min limit will hammer it
- Separate tool discovery (what can I call?) from tool invocation (how do I call it correctly?) — use descriptive names and short summaries for discovery, rich schemas for invocation

## Evidence

- **MCP Institute 2026 State Report:** Found 41% of surveyed software organizations in production with MCP servers, 400%+ YoY growth in production deployments, and that "tool description quality varies enormously" is the #1 reported pain point in enterprise deployments — [mcp.institute/research/state-of-mcp-2026](https://mcp.institute/research/state-of-mcp-2026)
- **Stacklok 2026 Software Report (via Digital Applied):** 41% of surveyed organizations in limited or broad MCP production. Replaced a prior unsourced claim of 78%. The strongest verified enterprise signal to date — [digitalapplied.com](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)
- **Digital Applied verification (May 2026):** MCP Registry API snapshot shows 9,652 active records, 28,959 total server/version records, and 15,926 GitHub repos with `mcp-server` topic — [digitalapplied.com](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)
- **HN thread on agent stack stratification (June 2026):** Noted that "the agent stack is splitting into specialized layers" and "sandboxing is becoming its own thing" — mentioning Shuru, E2B, Modal, and Firecracker wrappers as the execution isolation layer — [news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)

## Gotchas

- **Shipping MCP without reviewing descriptions is the equivalent of shipping an API without documentation.** The model will try to use it anyway, and will fail in creative ways.
- **Vague schema types (e.g., `any` or unconstrained strings) create a false sense of safety.** The model sees `type: string` and assumes any string works. Document the actual format.
- **Tool description updates often lag behind implementation changes.** A schema that was correct in January may mislead the model by March. Treat descriptions as versioned artifacts.
- **The MCP registry has quantity, not quality.** Many servers exist but aren't production-grade. Evaluate servers the same way you'd evaluate any dependency.
