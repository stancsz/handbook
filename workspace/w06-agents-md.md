# W-06 · AGENTS.md

One Markdown file at your repo root that tells every AI coding agent how your project builds, tests, and wants to be written — instead of one bespoke file per tool.

## Forces
- Through 2024–2025 each tool invented its own context file: `.cursorrules`, `CLAUDE.md`, `.github/copilot-instructions.md`, `CONVENTIONS.md` — a serious repo needed five near-identical copies
- An agent with no project context guesses your conventions and gets them wrong
- A file that's too long or auto-generated is worse than none — it burns tokens and misleads
- Tool-specific features still need tool-specific files; one format can't carry everything

## The move

- **Drop one `AGENTS.md` at the repo root.** Put the build setup, test commands, code conventions, and architectural constraints an agent needs to not guess. Plain Markdown, no schema.
- **Split shared from tool-specific.** Cross-tool instructions go in `AGENTS.md`; keep tool-specific knobs in their native files (`CLAUDE.md`, `.cursor/rules/`, `GEMINI.md`). Start with `AGENTS.md`; add the others only when you hit a real limitation.
- **Scope by directory.** Nearest file wins — a subpackage's `AGENTS.md` overrides the root for files under it. Use nested files for per-module rules.
- **Keep it minimal and frontmatter-free.** The spec stayed lean on purpose; that minimalism is what got 28+ tools to read it natively. Don't bloat it.
- **Write it by hand.** Reported research finds auto-generated / LLM-written agent files perform *worse* than no file at all, while human-curated ones give a small measurable gain. Curate; don't generate-and-commit.

## Receipt
> AGENTS.md originated with OpenAI (2025) and is now governed by the Linux Foundation's Agentic AI Foundation (formed December 2025). Reported reach as of mid-2026: 60,000+ repositories, 28+ tools reading it natively (Codex, GitHub Copilot, Cursor, Windsurf, Devin, Aider, Zed, VS Code, JetBrains Junie). Claude Code's native format is `CLAUDE.md` (this repo runs on one, kept local); its AGENTS.md support has been evolving through 2026, so verify behavior against your installed version. The "auto-generated files underperform no file" finding is reported from third-party research — directionally consistent across sources, but benchmark your own before trusting the magnitude. Sources verified 2026-06-25.

## See also
[W-02](w02-claude-code.md) · [S-13](../stacks/s13-context-engineering.md) · [W-01](w01-ai-dev-environment.md) · [S-10](../stacks/s10-mcp.md)

## Go deeper
Keywords: `AGENTS.md` · `CLAUDE.md` · `Agentic AI Foundation` · `.cursor/rules` · `copilot-instructions` · `nearest-file-wins` · `coding agent context`
