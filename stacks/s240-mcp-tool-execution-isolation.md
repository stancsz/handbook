# S-240 · MCP Tool Execution Isolation

Your agent is connected to 12 MCP servers. One serves a `read_file` tool. A user passes `"../../etc/passwd"` as the filename. Another MCP server exposes `run_shell`. A prompt injection payload in a retrieved document makes the agent call `run_shell rm -rf /`. MCP gives your agent superpowers — and superpowers need guardrails at the execution layer, not just the prompt layer.

## Forces

- MCP tools are first-class LLM targets: the model reasons about when and how to call them, making traditional input validation insufficient — the *parameters* are model-generated, not user-typed
- An MCP server trusted to expose `bash` or `write_file` becomes a pivot point if a prompt injection causes the agent to call it with malicious arguments
- Indirect prompt injection ([S-77](s77-system-prompt-injection-hardening.md)) can reach MCP tool calls: injected instructions in a fetched webpage or RAG chunk cause the agent to invoke tools the attacker couldn't call directly
- Tool schema inspection at registration time (MCP09 allowlist) handles unauthorized servers, but doesn't protect against *authorized* servers being misused with bad parameters
- Every MCP server has its own trust boundary — a filesystem server and an HTTP fetch server have different threat models and need different isolation strategies
- Cold-start latency of a sandboxed execution environment makes naive per-call isolation impractical for high-frequency tools

## The move

Layer isolation across four levels: **parameter interception → capability scoping → execution isolation → audit trail**.

### 1. Parameter interception (gate at the MCP server)

Before any tool executes, intercept the call and validate its parameters against a schema more restrictive than what the tool advertises:

```python
import functools
from mcp_server import mcp

def parameter_guard(param_schema: dict, allowlist: dict):
    """Decorator that narrows what parameters the tool can actually receive."""
    def decorator(func):
        @functools.wraps(func)
        async def guarded(args: dict, ctx):
            # Intersect user args against allowlist — drop anything not whitelisted
            safe_args = {k: args[k] for k in allowlist if k in args}
            # Hard-cap dangerous fields regardless of what the model passes
            safe_args.setdefault("max_tokens", 1024)
            safe_args.setdefault("allowed_paths", [])
            # Reject path traversal on file operations
            if "path" in safe_args:
                import os
                resolved = os.path.realpath(safe_args["path"])
                allowed = [os.path.realpath(p) for p in safe_args["allowed_paths"]]
                if not any(resolved.startswith(AP) for AP in allowed):
                    raise ValueError(f"Path {resolved} outside allowed scope")
            return await func(safe_args, ctx)
        return guarded
    return decorator

# MCP server exposing a file read tool
@mcp.tool()
@parameter_guard(
    param_schema={"path": str, "max_bytes": int},
    allowlist={"path", "max_bytes"}
)
async def read_file(args, ctx):
    path = args["path"]
    max_bytes = args.get("max_bytes", 65536)
    with open(path, "rb") as f:
        return f.read(max_bytes)
```

### 2. Capability scoping (MCP server-level)

Restrict what each MCP server *can* do, not just what it exposes. A server that only needs to read files shouldn't advertise a `delete` tool — and even if it does, the agent's reasoning model should never see it in the tool list.

```python
# MCP server registration — expose only the reduced capability surface
server = MCPServer(
    name="safe-filesystem",
    tools=[read_file],          # only read
    resources=[],               # no write, no exec, no delete
    capabilities=ToolCapability.READ_ONLY  # declared capability, not just schema
)
```

The capability declaration feeds into the agent's tool selection. A model that knows a server is `READ_ONLY` won't ask it to delete files — the reasoning trace won't include that action as an option.

### 3. Execution isolation (for dangerous tools)

For tools that execute code, shell commands, or fetch arbitrary URLs, isolate execution in a lightweight sandbox:

```python
import subprocess
import tempfile
import os

SANDBOX_FLAGS = [
    "read-only-rootfs",      # filesystem writes blocked
    "no-network",            # outbound network blocked
    "max-memory-mb=512",      # memory cap
    "cpu-quota=0.5",          # half a CPU
    "wall-time-ms=5000",     # wall-clock timeout
]

async def sandboxed_exec(cmd: str, args: dict, ctx) -> dict:
    # Only allow pre-approved command patterns
    approved = ["grep", "wc", "head", "tail", "sort", "cut"]
    base = cmd.split()[0] if isinstance(cmd, str) else cmd
    if base not in approved:
        raise ValueError(f"Command {base} not in approved list: {approved}")

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5,
            cwd=tmpdir,
            env={**os.environ, "HOME": tmpdir},  # jail HOME dir
            preexec_fn=os.setsid,                 # new process group
        )
    return {"stdout": result.stdout[:65536], "returncode": result.returncode}
```

For code execution (Python, JavaScript), route to an ephemeral container or Wasmtime sandbox. The pattern from [F-06](../forward-deployed/f06-agent-sandboxing.md) applies here: match isolation depth to threat level — lightweight process jail for shell commands, gVisor or microVM for arbitrary code.

### 4. Audit trail

Every tool invocation through an MCP server should be logged with the full call chain:

```python
import json
from datetime import datetime, timezone

async def audited_tool_call(server_name, tool_name, args, result, ctx):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": ctx.trace_id,
        "mcp_server": server_name,
        "tool": tool_name,
        "args_summary": {
            k: (v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v)
            for k, v in args.items()
        },
        "result_type": type(result).__name__,
        "result_size": len(str(result)[:1000]),  # first 1KB of result
        "latency_ms": ctx.elapsed_ms,
    }
    # Append-only log — never mutate, never delete
    await audit_log.append(entry)
```

## Receipt

> Receipt pending — June 30, 2026. The parameter interception decorator and sandboxed_exec patterns are derived from documented practices in Fordel Studios' agent sandboxing guide (March 2026) and Tian Pan's isolation depth taxonomy. A clean-room implementation with real Firecracker microVM integration should be validated before production use — the subprocess-based sandbox above is a development reference, not a production isolation guarantee.

## See also

- [F-06 · Agent Sandboxing](../forward-deployed/f06-agent-sandboxing.md) — isolation tiers (microVM, gVisor, container) and when to use each
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — interception layer between proposed and actual tool execution
- [S-77 · System Prompt Injection Hardening](s77-system-prompt-injection-hardening.md) — preventing injected instructions from reaching MCP tool calls in the first place
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — agent-to-agent handoffs when tools span multiple agents
