# S-412 · Code-Writing Agents Beat JSON Tool Schemas

JSON tool schemas are the default — and increasingly, a footgun. When the LLM must emit a structured JSON object describing which tool to call, every multi-step operation pays a tax: verbose serialization, awkward tool composition, and three round trips where one should suffice. A growing body of evidence from production teams and framework authors points to a simpler primitive: agents that write code.

## Forces

- **JSON serialization is a tax on every tool interaction.** The LLM emits structured JSON, the runtime parses it, executes the tool, and feeds the result back. Chain three operations and you've built a pipeline that could have been three lines of Python. The overhead compounds with the number of tools.
- **The tutorial cliff is real.** Multiple teams report that frameworks promising "build an agent in 5 lines" collapse the moment anything production-grade is required. Xpress AI went through five agent frameworks before stabilizing — each died on the same wall: silent failures under extended operation.
- **Code generation closes the gap between what the LLM thinks and what executes.** When the LLM generates Python code that calls real functions, tool composition becomes natural function calls instead of structured objects. Parallel tool calls are just sequential code lines.

## The Move

Smolagents (Hugging Face, released December 2024) makes this the core architectural primitive:

```python
from smolagents import CodeAgent, DuckDuckGoSearchTool, HfApiModel

agent = CodeAgent(tools=[DuckDuckGoSearchTool()], model=HfApiModel())
agent.run("How many seconds would it take for a leopard at full speed to run through Pont des Arts?")
```

The agent generates Python code that calls tools directly. Multi-step workflows are just sequential function calls in generated code.

- **Fewer round trips.** Where JSON-based systems need a parse → execute → feed-back cycle per tool, code-writing agents can chain multiple operations in one generated block.
- **Parallel tool calls via synchronous-looking code.** The LLM is prompted to emit parallel calls by writing code that calls tools simultaneously (or in a natural synchronous-looking sequence).
- **Lower prompt overhead.** No tool schema descriptions in the system prompt — tools are just Python functions with type hints and docstrings.
- **Sandboxing handles the obvious risk.** E2B or similar code execution sandboxes isolate LLM-generated Python from production infrastructure.
- **Local models work better at small sizes.** Code generation as a task is more learnable by smaller open models (7B–13B) than multi-step JSON tool calling, which requires strong instruction-following.

## Evidence

- **Hugging Face Blog:** Announced smolagents as successor to `transformers.agents`, arguing code-writing agents are "superior to JSON-based tool calling" for tool composition. The minimal example requires only `HfApiModel()` and a list of Python functions. — [https://huggingface.co/blog/smolagents](https://huggingface.co/blog/smolagents)
- **Hacker News (543 points, 88 comments):** User rdedev: "This is why I am leaning towards making the LLM generate code that calls operates on tools instead of having everything in JSON." User pferde confirmed "the neat part — there is none!" (the framework overhead disappears when you write code). — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **r/LocalLLaMA:** Users report that smolagents works better than CrewAI/LangChain for local models at 7B scale, where JSON tool calling fails more often. The recommendation: "copy the API and make your own framework" because most of it is "simple prompt engineering which can be achieved by simple string formatting." — [https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms](https://www.reddit.com/r/LocalLLaMA/comments/1bskjki/llm_agent_platforms)
- **Framework comparison (Lushbinary, April 2026):** Notes that smolagents is gaining adoption for its minimal design, contrasting with CrewAI's dependency on LangChain and LangGraph's graph complexity. — [https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/](https://lushbinary.com/blog/langgraph-vs-crewai-vs-autogen-ai-agent-framework-comparison/)

## Gotchas

- **Code execution sandboxing is non-negotiable.** Never run LLM-generated Python against production infrastructure without isolation (E2B, Firecracker, or similar). The attack surface is direct code execution.
- **Smaller models (≤7B) need careful prompting for complex code generation.** Code-writing works well for linear workflows; deeply nested or branching generated code degrades faster than simple tool-calling at small model sizes.
- **Debugging generated code is harder than debugging JSON.** When the LLM writes buggy code, the failure is a traceback, not a "malformed tool call" error. Invest in structured error translation back to the agent's scratchpad.
- **Not all teams need this.** If you have 3–5 tools with clear interfaces and no complex composition, JSON tool calling with a simple loop is fine. Code-writing agents pay off when tool chains are deep and composition is non-trivial.
