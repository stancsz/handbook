# S-20 · Agent Skills

A folder — `SKILL.md` plus optional files — that teaches an agent *how* to do a task, loaded into context only when it's actually needed. The procedure layer that sits beside MCP's capability layer ([S-10](s10-mcp.md)).

## Forces
- Pasting every workflow into the system prompt burns context whether or not the task needs it
- Loading every MCP tool's schema at session start can eat the majority of the window before the agent acts
- But an agent with no encoded procedure re-derives the same workflow, inconsistently, every time
- A skill only fires if the agent realizes it's relevant — and at discovery it sees almost nothing

## The move

- **Package the "how" as a skill.** A folder with a `SKILL.md` (YAML frontmatter: `name` + `description`, then instructions) plus optional `scripts/`, `references/`, `assets/`. It encodes a workflow, not a connection.
- **Lean on progressive disclosure — three stages.** (1) *Discovery*: only each skill's `name` + `description` sit in context at startup (tens of tokens each). (2) *Activation*: the full `SKILL.md` body loads only when a task matches the description. (3) *Execution*: referenced files load, and bundled scripts run via bash so only their **output** enters context. This is the context-engineering ([S-13](s13-context-engineering.md)) discipline made into a packaging format.
- **Keep many skills on hand cheaply.** Because only descriptions are always-resident, dozens of skills cost a small catalog — versus a fat prompt or all-tools-upfront MCP.
- **Skills and MCP are complementary, not rivals.** MCP = *capabilities* (what the agent can do: tools, data); Skills = *procedures* (how to run the workflow). Heuristic: need to **connect** to something → MCP; need to **teach** the agent how to approach something → Skill.
- **Invest in `name` and `description`.** They're all the agent sees at discovery, so they decide whether the skill ever triggers. Keep `SKILL.md` lean (under ~500 lines); push rarely-needed detail into reference files the body links to.

## Receipt
> This repo ships a working skill — `.claude/skills/handbook.md` (the `/handbook` navigator, ~2KB), a real instance of the pattern (Claude Code's skill format; the cross-tool standard adds YAML `name`/`description` frontmatter). Mechanism and token figures from Anthropic's [Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) writeup and analyses of its 17 official skills: discovery cost ≈55–235 tokens/skill (median ~80), activated bodies ~275–8,000 tokens (median ~2,000). Agent Skills became an open standard on 2025-12-18, since adopted across Claude Code, OpenAI Codex, Gemini CLI, GitHub Copilot, and Cursor. Verified 2026-06-25; token figures are reported, not independently measured here.

## See also
[S-28](s28-progressive-disclosure.md) · [S-10](s10-mcp.md) · [W-06](../workspace/w06-agents-md.md) · [S-13](s13-context-engineering.md) · [S-03](s03-tool-use.md)

## Go deeper
Keywords: `Agent Skills` · `SKILL.md` · `progressive disclosure` · `MCP vs Skills` · `capability vs procedure` · `context window` · `skill discovery` · `bash tool`
