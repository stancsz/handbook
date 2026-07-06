# S-205 · Agent Sandbox Isolation

When your agent calls `exec_sql`, `write_file`, or `send_email`, the tool runs in the same process — and with the same permissions — as the agent itself. A prompt injection, a bad LLM decision, or a tool returning unexpected data means the attacker already has your credentials. Sandboxing moves tool execution into an isolated environment with zero access to the host's secrets, filesystem, or network. No isolation means your agent is a privileged user with no accountability.

## Forces

- Agents are trusted to reason but untrusted to execute — the gap between "the model decided to call a tool" and "the tool accessed production infra" is where incidents happen
- Shared-process tool execution means every tool sees every credential loaded by every other tool — one poisoned tool compromises the entire stack
- Sandboxing technologies vary wildly in startup latency, isolation strength, and operational complexity — the wrong choice is either too slow or too loose
- Cold-start overhead makes naive sandboxing unusable for latency-sensitive agents; warm pools introduce idle cost and security state
- Framework-level isolation (LangChain tools in-process) provides zero real security — it stops curious prompts, not attacker-controlled tool calls
- Kubernetes SIG Apps launched `kubernetes-sigs/agent-sandbox` in late 2025, formalizing sandbox lifecycle as a distinct concern from the isolation technology itself

## The move

**Three isolation tiers, matched to threat level:**

| Threat level | Use case | Technology | Startup |
|---|---|---|---|
| Internal, same privilege | Code analysis, data transform | Docker container (rootless) | ~1s |
| Cross-user, reduced privilege | SaaS tool execution, user-provided code | gVisor (runsc), Kata Containers | ~500ms |
| Untrusted, adversarial | Generated code from external prompts, plugin sandbox | Firecracker MicroVM, WebAssembly (Wasmtime) | 100ms (pre-warmed) |

**The canonical sandbox lifecycle:**

```
User request
  → Provision sandbox (or pull from warm pool)
  → Execute agent tool calls inside sandbox
  → Optional: snapshot/checkpoint session state
  → On completion: destroy sandbox
  → On error: rollback to last snapshot or abort
```

**Minimal implementation with Firecracker:**

```python
import json
import subprocess
import uuid
import firecracker_sdk  # PyPI: firecracker-sdk

class SandboxedToolExecutor:
    """Run agent tool calls inside an ephemeral Firecracker MicroVM."""

    def __init__(self, kernel_path: str, initrd_path: str, memory_mb: int = 256):
        self.kernel_path = kernel_path
        self.initrd_path = initrd_path
        self.memory_mb = memory_mb
        self.active_vms: dict[str, firecracker_sdk.MicroVM] = {}

    def exec_in_sandbox(
        self,
        tool_name: str,
        params: dict,
        allowed_files: list[str] | None = None,  # filesystem allowlist
        allowed_hosts: list[str] | None = None,  # network allowlist
        timeout_s: int = 30,
    ) -> dict:
        # Each VM is ephemeral: created per-task, destroyed after
        vm_id = str(uuid.uuid4())
        vm = firecracker_sdk.MicroVM(vm_id)
        vm.start(
            kernel=self.kernel_path,
            initrd=self.initrd_path,
            memory_mb=self.memory_mb,
            # Network: deny all except explicitly allowed hosts
            network_policy="deny",
            # Filesystem: read-only except allowed paths
            readonly_fs=["/usr", "/lib"],
            writable_fs=allowed_files or [],
            # CPU limits prevent cryptomining / DoS within sandbox
            vcpus=1,
        )

        try:
            result = vm.run_json({
                "action": tool_name,
                "params": params,
                "allowed_hosts": allowed_hosts or [],
            }, timeout=timeout_s)
            return {"status": "ok", "result": result}
        except firecracker_sdk.TimeoutError:
            return {"status": "timeout", "tool": tool_name, "limit_s": timeout_s}
        except firecracker_sdk.SandboxViolation as e:
            # Tool tried to access unauthorized resource
            return {"status": "violation", "tool": tool_name, "reason": str(e)}
        finally:
            # Always destroy — no state persists between tasks
            vm.stop()
            del self.active_vms[vm_id]

    def exec_in_warm_pool(self, tool_name: str, params: dict, **kwargs) -> dict:
        """Pre-warmed VM for latency-critical paths. Pool must be warmed during idle."""
        # Pool management: maintain N VMs in "ready" state
        # When a request arrives, assign it a warm VM instead of cold-starting
        warm_vm = self._pool_get()
        if warm_vm is None:
            return self.exec_in_sandbox(tool_name, params, **kwargs)
        try:
            return warm_vm.run_json({"action": tool_name, "params": params}, timeout=kwargs.get("timeout_s", 30))
        finally:
            self._pool_return(warm_vm)

    def _pool_get(self):
        # Simple queue: pop a pre-warmed VM, return it for immediate use
        raise NotImplementedError("Use a thread-safe queue of warmed VMs")

    def _pool_return(self, vm):
        raise NotImplementedError("Reset VM state, re-queue for next task")
```

**Security checklist for every agent deployment:**

- [ ] Credential binding: tools get scoped credentials, not host credentials. If the sandbox is breached, blast radius is limited to the tool's intended scope
- [ ] Filesystem allowlist: block access to `/etc/secrets`, `$HOME/.aws`, SSH keys, and any path containing tokens
- [ ] Network deny-by-default: explicitly whitelist `api.stripe.com` but deny `*.internal`
- [ ] Snapshot on entry: before any tool executes, record the VM state so you can roll back after a compromised or buggy tool
- [ ] Log all system calls: you can't alert on what you can't see — capture `mmio`, `ioctl`, and network events inside the sandbox
- [ ] Kill switch: every sandbox must have a hard timeout and a parent-process abort path. If the orchestrator dies, the sandbox must die with it

**For gVisor (simpler, slower, Kubernetes-native):**

```yaml
# Kubernetes pod spec with gVisor runtime
spec:
  runtimeClassName: gvisor
  containers:
  - name: agent-executor
    image: agent-tool-runtime:latest
    securityContext:
      # gVisor enforces this via seccomp + user namespaces
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
    resources:
      limits:
        memory: "512Mi"
        cpu: "500m"
```

## Receipt

> Receipt pending — June 29, 2026

## See also

- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — the interception layer that gates which tools can be called
- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — MCP's trust amplification problem and protocol-level mitigations
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — time/budget limits that stop runaway agents; sandbox isolation is the complementary blast-radius reduction
