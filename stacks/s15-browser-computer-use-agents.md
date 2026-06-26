# S-15 · Browser and Computer-Use Agents

Agents that drive a real browser or OS — clicking, typing, reading the screen — to do tasks no API exposes. Powerful, and the least reliable layer you'll ship.

## Forces
- Most of the world's software has a UI but no API; a computer-use agent is the only way in
- Reliability is the core problem: reported success runs 30–89% depending on tool and task — fully autonomous multi-step work still needs human checkpoints
- The agent runs with the user's full authenticated privileges, so a single hijacked step can touch banking, email, and cloud storage
- Vision is flexible but slow and imprecise; DOM is fast and exact but breaks on non-standard UI

## The move

The tooling (2026): Anthropic Computer Use, OpenAI's CUA / ChatGPT agent, `browser-use` (Python on Playwright), Playwright MCP ([S-10](s10-mcp.md)), Microsoft Copilot Studio computer use. Pick by where it embeds; the reliability techniques below apply to all.

- **DOM first, vision as fallback.** Read the DOM for targeting — it's faster, gives exact element references, and handles content below the fold. Fall back to vision only for canvas or non-standard UI.
- **Blend deterministic scripts with AI.** Script the predictable steps; let the agent handle the dynamic parts. Add deterministic safe-fallback overrides for ambiguous states.
- **Run as a plan-follower with human checkpoints.** Gate irreversible or sensitive steps on human approval. Browser Use reported success jumping from ~30% to ~80% switching from full autonomy to this model.
- **Treat every page as untrusted, and sandbox.** Indirect prompt injection is systemic ([F-04](../forward-deployed/f04-guardrails.md)). Run the agent in a sandbox ([F-06](../forward-deployed/f06-agent-sandboxing.md)) and require human approval for any action touching auth, money, or data egress.
- **Delegate the plumbing at scale.** Managed browser infra (Browserbase, Firecrawl) handles proxies, CAPTCHAs, and fingerprints so you're not running a headless fleet.

## Receipt
> Tool landscape and the 30–89% success range sourced from 2026 browser-automation surveys (Browserless, Firecrawl, Optexity); the ~30%→~80% plan-follower gain is Browser Use's own reported figure — directional, not a guarantee; benchmark your task. Security: Brave's security team disclosed (Aug 2025) that Perplexity's Comet browser, asked to "summarize this webpage," executed attacker instructions hidden in the page and could exfiltrate the user's credentials — [writeup](https://brave.com/blog/comet-prompt-injection/); a follow-up (Oct 2025) hid the same payloads in screenshots. The root cause (trusted instructions and untrusted content share one token stream) has no clean fix as of mid-2026. Verified 2026-06-25; not independently reproduced here.

## See also
[S-03](s03-tool-use.md) · [S-10](s10-mcp.md) · [F-04](../forward-deployed/f04-guardrails.md) · [F-06](../forward-deployed/f06-agent-sandboxing.md) · [F-05](../forward-deployed/f05-agent-failure-taxonomy.md)

## Go deeper
Keywords: `computer use` · `browser agents` · `Anthropic Computer Use` · `browser-use` · `Playwright MCP` · `indirect prompt injection` · `DOM vs vision` · `Browserbase` · `human-in-the-loop`
