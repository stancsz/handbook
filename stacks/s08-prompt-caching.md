# S-08 · Prompt Caching

When the same large prefix repeats across requests, cache it — pay for it once, reuse it many times.

## Forces
- Long system prompts and document contexts are re-sent (and re-billed) on every request
- In agentic loops, the system prompt and tool definitions repeat thousands of times
- Caching cuts input cost dramatically for read-heavy workloads
- Cache misses still cost full price; caching only pays on repetition

## The move

**Anthropic prompt caching (as of 2026):**

Mark the cacheable prefix with `"cache_control": {"type": "ephemeral"}`. The first request pays full price and populates the cache. Subsequent requests that share the identical prefix pay ~10% of the input token cost.

```python
import anthropic

client = anthropic.Anthropic()

# Large document / system prompt you'll reuse
LONG_DOCUMENT = "..." * 5000  # your large context

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": LONG_DOCUMENT,
            "cache_control": {"type": "ephemeral"}  # mark for caching
        }
    ],
    messages=[{"role": "user", "content": "Summarize section 3."}]
)

# Check cache usage in the response
print(response.usage)
# cache_creation_input_tokens: charged at full rate on first call
# cache_read_input_tokens: charged at ~10% on subsequent calls
```

**When it pays off:**
- Repeated queries against the same document (Q&A, chatbots over a corpus)
- Agentic loops with a fixed system prompt + tools
- Multi-turn conversations with a large shared context

**Cache TTL:** approximately 5 minutes on Anthropic's API (as of 2026). After that, the next request re-populates.

## Receipt
> Receipt pending — 2026-06-25. API syntax above follows Anthropic's prompt caching documentation. Exact cost ratios and TTL: verify at docs.anthropic.com/prompt-caching before relying on them for budget calculations.

## See also
[S-02](s02-context-budget.md) · [S-06](s06-model-routing.md) · [S-07](s07-rag.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper
Keywords: `prompt caching` · `KV cache` · `Anthropic cache_control` · `OpenAI prompt caching` · `prefix caching`
