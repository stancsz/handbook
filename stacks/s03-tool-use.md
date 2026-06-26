# S-03 · Tool Use

Give the model hands — the ability to call functions, read files, hit APIs, and act on the world.

## Forces
- An LLM alone can only generate text — it can't fetch live data, run code, or persist state
- Tools make agents possible; without them you have a chatbot
- More tools = more surface area for failure; every tool is a trust boundary
- The model decides *when* to call a tool — that decision can be wrong

## The move

Define tools as JSON schemas. Pass them with the request. The model returns a `tool_use` block when it wants to invoke one; you execute it and return the result.

**Minimal example (Anthropic SDK):**
```python
import anthropic

client = anthropic.Anthropic()
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    }
]

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Tokyo?"}]
)

# Check if the model wants to use a tool
if response.stop_reason == "tool_use":
    tool_call = next(b for b in response.content if b.type == "tool_use")
    print(f"Tool: {tool_call.name}, Input: {tool_call.input}")
```

**Key patterns:**
- Keep tool descriptions precise — the model uses them to decide when to call
- Return structured results, not prose — the model re-parses your return value
- Limit the tool set per call; 5–10 tools is usually the practical ceiling before reliability degrades
- Always validate tool inputs server-side — the model can hallucinate parameter values

## Receipt

> Verified 2026-06-25 — run against llama3.2 via Ollama (localhost:11435). Pattern is model-agnostic; same stop_reason/block structure applies on Anthropic API.

```
$ node poc_tool_use.cjs
Stop reason: tool_use
Block type: text
Text: 42
Block type: tool_use
Tool called: add_numbers
Input: {"a":15,"b":27}
Tokens: in=2778 out=34
```

**Two findings from the receipt:**
- The model emitted a text block ("42") *before* calling the tool — it answered in prose and called the tool. This is valid `tool_use` behavior; your parser must handle mixed content blocks, not assume tool_use is always the only block.
- 2778 input tokens for a single tool definition. Ollama serializes tool schemas verbosely; hosted APIs are more efficient. Count your tool tokens before adding many tools to a tight context budget.

## See also
[S-19](s19-agent-loop.md) · [S-04](s04-structured-output.md) · [S-10](s10-mcp.md) · [S-05](s05-multi-agent-patterns.md)

## Go deeper
Keywords: `function calling` · `tool use` · `Anthropic tool_use` · `OpenAI function calling` · `agentic loop` · `ReAct pattern`
