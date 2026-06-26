# S-02 · Context Budget

The context window is the core constraint of every LLM call. Treat it like memory: finite, expensive, and worth managing.

## Forces
- Models have hard token limits (often 128K–1M tokens depending on the model)
- Every input token costs money; output tokens cost more
- Putting everything in context is the lazy path — it bloats cost and dilutes signal
- Too little context and the model lacks what it needs to reason correctly

## The move

Think of the context window as a budget, not a bucket.

**What goes in (in order of priority):**
1. Task instruction (system prompt) — the fewest words that fully define the job
2. The minimum data the model needs to answer — retrieve, don't dump
3. Few-shot examples — only when they measurably improve output
4. Prior conversation turns — prune old turns that no longer affect the answer

**Rules of thumb:**
- If an input token doesn't change the output, it shouldn't be there
- Summarize long documents before injecting them — see [S-07 RAG](s07-rag.md)
- Count tokens before you assume something fits: `claude -p` will error on overflow, not silently truncate

**Token counting (Anthropic API):**
```python
import anthropic
client = anthropic.Anthropic()
response = client.messages.count_tokens(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "your prompt here"}]
)
print(response.input_tokens)
```

## Receipt
> Receipt pending — 2026-06-25. Token count API call above is from Anthropic documentation; run it against your prompt to get actual numbers.

## See also
[S-18](s18-tokenization.md) · [S-08](s08-prompt-caching.md) · [S-07](s07-rag.md) · [S-01](s01-local-model-dispatch.md) · [S-56](s56-preflight-token-check.md)

## Go deeper
Keywords: `token counting` · `context window` · `prompt compression` · `LLMLingua` · `sliding window attention`
