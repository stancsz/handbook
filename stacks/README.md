# Book of Patterns

The moves, techniques, and architectures agents are built from. Each entry is a named pattern — a situation, the forces in tension, the actual technique, and a receipt from reality.

Three tiers, ten entries each:

---

### Foundations

The primitives. What every agent needs before it needs anything else.

| Code | Name | One-liner |
|---|---|---|
| [S-01](s01-local-model-dispatch.md) | Local Model Dispatch | Run inference locally, zero API cost |
| [S-02](s02-context-budget.md) | Context Budget | Fit what matters into the window |
| [S-03](s03-tool-use.md) | Tool Use | Give the model hands |
| [S-04](s04-structured-output.md) | Structured Output | JSON that doesn't break your pipeline |
| [S-05](s05-multi-agent-patterns.md) | Multi-Agent Patterns | Fan-out, pipeline, supervisor |
| [S-06](s06-model-routing.md) | Model Routing | Right model for right task |
| [S-07](s07-rag.md) | RAG | When the model needs to read |
| [S-08](s08-prompt-caching.md) | Prompt Caching | Cut repeated-context costs by 90% |
| [S-09](s09-memory-systems.md) | Memory Systems | What persists between calls |
| [S-10](s10-mcp.md) | MCP | Extend any model with tools |

---

### Architecture

The components. How agents are wired together, deployed, and exposed.

| Code | Name | One-liner |
|---|---|---|
| [S-11](s11-llm-gateway-fallback.md) | LLM Gateway and Fallback | Survive the outage your provider will have |
| [S-12](s12-streaming.md) | Streaming Response Delivery | Stream to humans, not to code |
| [S-13](s13-context-engineering.md) | Context Engineering | The smallest high-signal token set that works |
| [S-14](s14-a2a-protocol.md) | A2A Protocol | The agent-to-agent layer beside MCP |
| [S-15](s15-browser-computer-use-agents.md) | Browser and Computer-Use Agents | Drive real UIs; the least reliable layer |
| [S-16](s16-prompting.md) | Prompting | How to phrase the ask, by model family |
| [S-17](s17-embeddings.md) | Embeddings | Text as vectors; the basis of RAG and memory |
| [S-18](s18-tokenization.md) | Tokenization | What a token is, and why it's the bill |
| [S-19](s19-agent-loop.md) | The Agent Loop | Reason-act-observe; what makes it an agent |
| [S-20](s20-agent-skills.md) | Agent Skills | SKILL.md; teach the how, load it only when needed |

---

### Reasoning & Quality

The moves that improve accuracy, reduce hallucination, and manage uncertainty at inference time.

| Code | Name | One-liner |
|---|---|---|
| [S-21](s21-context-compaction.md) | Context Compaction | Summarize old turns, continue in a fresh window |
| [S-22](s22-tool-selection-at-scale.md) | Tool Selection at Scale | Retrieve the right tools; don't dump all of them |
| [S-23](s23-workflows-vs-agents.md) | Workflows vs Agents | Default to a workflow; add autonomy only where needed |
| [S-24](s24-self-consistency.md) | Self-Consistency | Sample k chains, take the majority vote |
| [S-25](s25-reflection.md) | Reflection | Generate, critique, refine — with a stop rule |
| [S-26](s26-planning.md) | Planning | Decompose into subtasks, then execute |
| [S-27](s27-reranking.md) | Reranking | Recall wide, then rerank for precision |
| [S-28](s28-progressive-disclosure.md) | Progressive Disclosure | Index first; load the body only when needed |
| [S-29](s29-false-consensus.md) | False Consensus | Agreement isn't truth; vote only over independent samples |
| [S-30](s30-code-test-fix-loop.md) | Code-Test-Fix Loop | Test execution is the oracle; self-review is a probabilistic bet |
| [S-31](s31-prompt-compression.md) | Prompt Compression | Compress retrieved passages before injection; compress once, save on every query |
| [S-355](s355-agent-autonomy-levels-bounded-autonomy.md) | Agent Autonomy Levels | Classify agents L0–L5; enforce the read-to-write escalation gate |

---

### Governance & Autonomy

| Code | Name | One-liner |
|---|---|---|
| [S-340](s340-agent-hard-enforcement-plane.md) | Agent Hard Enforcement Plane | Hard cost caps, loop bounds, escalation gates — before they compound |
