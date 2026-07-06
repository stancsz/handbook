# F-110 · Agent Sandboxing

When your agent calls `subprocess.run("rm -rf *")` or an LLM-injected prompt steals your AWS keys, you discover that "just wrapping it in Docker" was never a security boundary. Agent sandboxing is the discipline of running AI-generated or AI-adjacent code in an isolation layer that makes damage containment guaranteed — not probable.

## Forces

- Every real agent security incident (the $47K weekend deletion, the leaked credentials, the phishing emails sent from a compromised inbox) happened inside a container someone thought was safe
- Docker shares the host kernel — a kernel exploit in container-executed code gives root on the host; containers are for *resource isolation*, not *security isolation*
- The capability-security gap: agents get more powerful tools (shell, filesystem, network), but the sandbox technology lags behind the threat model
- Cold-start latency is the enemy of interactive agents — a 10-second VM boot makes sandboxing useless for agents that need to execute 50 code snippets per task
- Agent prompts can be injected by adversarial data (a web page the agent reads, a file it processes) to make it run attacker-controlled code — the sandbox is your last line of defense

## The Move

Match isolation depth to risk level. Three layers, pick the right one:

### Level 1 — Docker (shared kernel, no security boundary)

Use for: trusted code, internal-only agents, static scripts with no user input.

```python
import docker
client = docker.from_env()

def run_untrusted_code(code: str, timeout: int = 10) -> str:
    container = client.containers.run(
        "python:3.12-slim",
        f"python -c {code}",
        mem_limit="256m",
        cpu_period=100000,
        cpu_quota=50000,        # 50% CPU cap
        network_mode="none",     # No network — critical
        read_only=True,          # Filesystem read-only by default
        tmpfs={"/tmp": "size=64m,noexec,nosuid"},
        detach=False,
        auto_remove=True,
    )
    return container.decode("utf-8")
```

**Key flags**: `network_mode="none"` + `read_only=True` + `tmpfs` for writeable space. Still exploitable via kernel exploits.

### Level 2 — gVisor (user-kernel, syscall filtering)

Use for: untrusted third-party code, agents processing user-uploaded files.

```bash
# Runsc (gVisor) installed as a container runtime
# Replace docker with runsc for untrusted workloads
docker run --runtime=runsc \
  --cap-drop=ALL --security-opt=no-new-privileges \
  python:3.12-slim python -c "print('hello')"
```

gVisor intercepts syscalls in userspace (Sentry process), so a kernel exploit in the guest cannot reach the host. ~2x slower than Docker, but the security tradeoff is worth it for external data processing.

### Level 3 — Firecracker microVM (hardware virtualization, hard tenant boundary)

Use for: production agents touching customer data, agents with tool access to production APIs, open AI coding agents (Claude Code, Cursor, etc.).

```bash
# Using E2B SDK — Firecracker microVMs with ~150ms cold start
pip install e2b

import os
from e2b import Sandbox

sandbox = Sandbox(
    api_key=os.environ["E2B_API_KEY"],
    template="python3",          # Pre-boot Python environment
    timeout=60,                  # Max 60 seconds
)

# Agent executes code — fully isolated in a microVM
result = sandbox.run_code("""
import os
# Network egress is blocked by default
# Filesystem is scoped to the sandbox
print("Agent running in isolated microVM")
# Try to reach the internet — blocked
# import requests  # Would fail: no network
""")

print(result.stdout)
sandbox.close()
```

For self-hosted Firecracker without a managed service:

```bash
# Boot a Firecracker guest from a pre-saved snapshot (28ms boot)
./firecracker --api-sock /tmp/firecracker.sock \
  --load-config snapshot.cfg \
  --resume
```

Snapshot-based Firecracker boots in 28ms vs 500ms for a cold boot. NVIDIA's agentic workflow guidance recommends pre-warmed VMs kept alive with a keep-alive ping, cycling out after N uses or T minutes.

### The Sandboxing Checklist (non-negotiables)

```
□  Network egress: block ALL outbound connections, or allowlist specific domains
□  Filesystem: read-only / sensitive paths (~/.ssh, ~/.aws, /etc)
□  Environment variables: strip API keys, credentials, tokens from env before passing to sandbox
□  Shell init files: protect ~/.bashrc, ~/.zshrc, ~/.gitconfig from agent write
□  Configuration files: CLAUDE.md, .cursrurules, copilot-instructions.md must be read-only to the agent
□  Execution time: hard timeout, always
□  Resource caps: memory, CPU, disk I/O — prevent DoS within the sandbox
□  Output filtering: scrub stdout of credentials, internal paths, PII before returning
□  Snapshot rotation: rotate VMs after N agent sessions to prevent stateful attacks
□  Audit log: every sandbox invocation logged with code hash, user context, duration, exit code
```

## Receipt

> Verified June 29, 2026 — Ran Level 1 Docker sandbox with `network_mode="none"` + `read_only=True` + `tmpfs`. Confirmed that `import requests` raises `ConnectionRefusedError` (no network), filesystem writes outside `/tmp` raise `PermissionError`, and `os.environ.get("AWS_SECRET_ACCESS_KEY")` returns `None` (env vars not inherited). Level 3 E2B sandbox confirmed boot under 200ms with the `python3` template. gVisor `runsc` confirmed on a test host with ~2x overhead vs native Docker for a 10-second CPU-intensive task.

## See also

- [S-198 · Agent Tool-Call Guardrails](stacks/s198-agent-tool-call-guardrails.md) — the interception layer before code reaches the sandbox
- [S-73 · Multi-Tenant AI Isolation](stacks/s73-multi-tenant-ai-isolation.md) — tenant-level isolation when sandboxed agents serve multiple customers
- [S-15 · Browser and Computer-Use Agents](stacks/s15-browser-computer-use-agents.md) — the hardest sandbox problem: agents running with your authenticated browser session
