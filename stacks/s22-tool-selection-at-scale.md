# S-22 · Tool Selection at Scale

An agent picks the right tool easily from three. Give it eighty and selection degrades, tokens balloon, and it starts hallucinating calls. The fix: retrieve tools instead of dumping them.

## Forces
- Every tool definition is context the model must read on *every* call — 80 tools is a tax paid per turn ([S-13](s13-context-engineering.md))
- Overlapping tools blur together; the model picks a plausible-but-wrong neighbor or invents a call
- Providers cap tools per request (~128) and accuracy degrades well before the cap — the practical ceiling is far lower
- But the collapse is *task-dependent*: clean, distinct descriptions on simple queries survive large lists; ambiguity and multi-step chains are what break it

## The move
- **Don't ship the whole toolbox.** Past ~20 tools, stop putting every definition in the prompt. Treat tools like documents and retrieve them.
- **RAG over tools.** Embed every tool description once; at request time embed the query and pass only the top-k most similar tools ([S-07](s07-rag.md), [S-17](s17-embeddings.md)). Reported to roughly triple selection accuracy and halve prompt tokens versus dumping all.
- **Add dependency awareness when tools chain.** Pure vector similarity misses "to call B you first need A." Graph-aware tool retrieval keeps required predecessors in the shortlist.
- **Prefer adaptive depth over a fixed top-k.** A short, query-dependent list both saves tokens *and* improves accuracy — too few and the right tool is absent; too many and it blurs. Let the shortlist length vary with the query.
- **Or partition by sub-agent.** Give each specialized agent its own small toolset ([S-05](s05-multi-agent-patterns.md)) — but each sub-agent still has its own ceiling, so retrieval still applies inside large ones.

This is [Law 1](../laws.md) (cheapest sufficient intelligence): send the fewest tools that can do the job, not every tool you own.

## Receipt
> Verified 2026-06-25 — same 5 ambiguous queries (each with one right tool and a near-competitor), few-tools vs many-tools, against llama3.2 via Ollama (localhost:11435). Tools carried one-line descriptions.

```
FEW (10 tools):  5/5 correct
MANY (75 tools): 5/5 correct
```

**Honest negative result:** with *clean, distinct descriptions* and *single-step queries*, the local model held 5/5 even at 75 tools — I did **not** reproduce the dramatic accuracy collapse at this scale. That collapse is documented at larger inventories on harder tasks: the Berkeley Function Calling Leaderboard reports calendar-task accuracy falling from **43% to 2%** as tools went from 4 to 51. The lesson stands either way — (1) at 75 tools every selection still paid to include all 75 definitions in context (the cost is unconditional), and (2) the accuracy cliff is real at scale/ambiguity even if a tidy 75-tool set dodges it. Retrieve to cut both risks. (My bridge's input-token counts were unreliable — a ~2,500-token floor — so the quantified token/accuracy figures are from the cited literature, not this run.)

## See also
[S-03](s03-tool-use.md) · [S-10](s10-mcp.md) · [S-07](s07-rag.md) · [S-13](s13-context-engineering.md) · [S-05](s05-multi-agent-patterns.md)

## Go deeper
Keywords: `RAG-MCP` · `tool retrieval` · `RAG over tools` · `Graph RAG-Tool Fusion` · `ScaleMCP` · `Berkeley Function Calling Leaderboard` · `adaptive top-k` · `Toolshed`
