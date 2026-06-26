# F-05 · Agent Failure Taxonomy

Multi-step, multi-tool, multi-agent systems fail in ways that single-call LLMs do not. These are the agentic-specific failure modes — the ones F-03 doesn't cover.

## Forces

- Errors compound silently: a wrong inference at step 2 propagates through 20 downstream steps with no exception raised
- Agents can loop indefinitely; there is no built-in terminal condition for "the thing you're looking for doesn't exist"
- Multi-agent systems introduce cross-agent trust and privilege boundaries that don't exist in single-model calls
- External content (tool results, web pages, emails) is an attack surface that single-call systems don't expose

## The move

Six failure classes. The first four are from Microsoft's agentic red-teaming taxonomy (12 months of testing, 2026); the last two are common production failure modes documented across the field. Each has a name, a description, and a fix.

---

**Supply chain compromise**  
A malicious tool or MCP server is inserted into the agent's tool registry. The agent calls it as trusted, executes attacker-controlled code, or leaks context.  
Fix: maintain a signed allowlist of approved tools. Treat tool registration like dependency management — review before adding. Pin MCP server versions.

---

**Goal hijacking**  
External content (a web page, an email, a file the agent retrieves) contains instructions that redirect the agent's goal mid-run. Classic prompt injection, but the surface area is every tool result.  
Fix: sandbox tool results — parse them as data, not instructions. Separate the planning prompt from retrieved content. Add a planner-verifier loop that checks whether the current goal matches the original task.

---

**Recursive hijacking**  
A goal modification in one reasoning step propagates through the agent's own chain-of-thought, compounding the redirect across multiple hops. The agent reasons its way into an attacker-controlled objective.  
Fix: freeze the root goal in a system prompt that reasoning steps cannot overwrite. Validate the current objective against the frozen root before each major step.

---

**Cross-agent privilege escalation**  
Agent A causes Agent B to act beyond its permissions. A orchestrates B and passes it a context or instruction that triggers B to use capabilities A itself doesn't have.  
Fix: each agent enforces its own permission boundary independently — don't inherit permissions from the caller. Treat inter-agent calls like API calls from an untrusted client.

---

**Silent error propagation**  
The agent returns well-formatted, confident output while the answer is wrong. A misunderstood instruction at step 2 propagates through 20 steps. No exception is raised, no retry is triggered. Harder to detect than a crash.  
Fix: structured intermediate outputs at each step. Evals that check intermediate state, not just final output. See [F-02](f02-evaluation-at-scale.md) for eval patterns.

---

**Infinite loop on missing information**  
When a target resource doesn't exist, the agent replans and retries indefinitely — no terminal condition is defined for "the thing you're searching for doesn't exist."  
Fix: explicit max-step budget enforced in the loop controller. Dead-end detection: N identical tool calls in a row = stop. Required "cannot complete" exit branch in every planning prompt.

---

**The Air Canada precedent (2024):** Air Canada's chatbot told a customer he could claim a bereavement fare retroactively — wrong, per the airline's own policy page. Air Canada argued the chatbot was "a separate legal entity responsible for its own actions." The British Columbia Civil Resolution Tribunal called that submission remarkable and held the airline liable for negligent misrepresentation (C$650.88 in damages). Agent failures are not shielded by the "it was the AI" defense. Your agent's output is your output.

## Receipt

> First four taxonomy classes sourced from Microsoft Security Blog, 2026-06-04 (12 months of agentic red-teaming). Silent error propagation and infinite-loop classes are widely documented production failure modes, not Microsoft-specific. Air Canada case verified against the ruling: Moffatt v. Air Canada, 2024 BCCRT 149 (British Columbia Civil Resolution Tribunal, February 2024) — negligent misrepresentation, C$650.88 damages. Verified 2026-06-25.

## See also

[F-03](f03-failure-modes.md) · [F-02](f02-evaluation-at-scale.md) · [S-05](../stacks/s05-multi-agent-patterns.md) · [S-10](../stacks/s10-mcp.md) · [F-10](f10-agent-identity-and-access.md)

## Go deeper

Keywords: `agentic AI red teaming` · `prompt injection multi-agent` · `MCP security` · `cross-agent privilege escalation` · `AI liability` · `goal hijacking`
