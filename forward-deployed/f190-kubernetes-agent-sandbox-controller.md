# F-190 · Kubernetes Agent Sandbox Controller

When your AI agent runs as a Deployment or a hacked-together StatefulSet, you don't have an agent — you have an operational liability. The kubernetes-sigs/agent-sandbox project fills the gap: a CNCF-backed CRD and controller that gives Kubernetes native primitives for long-running, stateful, singleton agent workloads with warm pools and pluggable isolation runtimes.

## Forces
- Kubernetes has no concept of "an agent." Deployments are for replicas, StatefulSets for ordered databases. Agents are neither.
- The "StatefulSet hack" — single-pod StatefulSet + headless Service + PVC — is brittle and requires manual lifecycle management
- Agents need persistent identity across restarts, warm standby capacity, and configurable isolation without YAML archaeology
- Only 5% of enterprise AI agents run in production with real authority (Cleanlab, 2026); platform primitives are a large part of why
- The agent-sandbox project (SIG Apps, CNCF) reached v0.5.0 in June 2026 with 3k GitHub stars — production-grade, not a hack

## The move

### The core problem: Kubernetes doesn't know what an agent is

```
# The StatefulSet Hack — before agent-sandbox
# Three separate resources to manage, zero lifecycle awareness

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-agent-data
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: Pod
metadata:
  name: my-agent
  labels:
    app: my-agent
spec:
  containers:
  - name: agent
    image: python:3.11-slim
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: my-agent-data
---
apiVersion: v1
kind: Service
metadata:
  name: my-agent
spec:
  clusterIP: None
  selector:
    app: my-agent
```

### The agent-sandbox way — one resource

```yaml
# install the CRD first: kubectl apply -k github.com/kubernetes-sigs/agent-sandbox
apiVersion: agents.x-k8s.io/v1alpha1
kind: Sandbox
metadata:
  name: my-agent
spec:
  runtimeClassName: kata-fc        # Firecracker via Kata Containers
  volumeClaimTemplates:            # declarative storage — controller provisions PVC
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 1Gi
  sandboxTemplate:                 # optional: inherit from a SandboxTemplate
    name: default-agent-template
  # Additional features:
  # persistentVolumeClaimTemplates for multi-volume
  # annotations/labels propagate to all child resources
```

### The four CRDs and when to use which

| CRD | When to use |
|-----|-------------|
| `Sandbox` | Direct declarative management of a single agent pod |
| `SandboxTemplate` | Codify a runtime configuration (image, runtimeClass, volumes, env) once, reuse it |
| `SandboxClaim` | User-facing; the controller provisions a Sandbox from a Template — good for multi-tenant or on-demand spawning |
| `SandboxWarmPool` | Pre-warm a pool of pods so allocation is near-instant (<100ms vs cold pod scheduling latency) |

### Warm pool — the latency fix that makes security usable

The cold-start tax is why teams disable sandboxing. `SandboxWarmPool` solves it:

```yaml
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: my-agent-pool
spec:
  minAvailable: 2          # always keep 2 warm pods ready
  sandboxTemplateRef:
    name: default-agent-template
  # Controller maintains N warm pods matching the template.
  # New sandbox requests from SandboxClaims get a warm pod instantly.
  # Pods are pre-scheduled, pre-pulled, pre-initialized.
```

### Pair with the right isolation runtime

agent-sandbox is **runtime-agnostic** — you pick via `runtimeClassName`:

| Runtime | runtimeClassName | Isolation level | KVM needed | Use case |
|---------|-----------------|-----------------|------------|----------|
| gVisor (runsc) | `gvisor` | Syscall interception | No | Local dev, macOS/Windows CI |
| Kata Containers | `kata` | VM-grade (full kernel) | Yes | Multi-tenant prod |
| Kata + Firecracker | `kata-fc` | MicroVM (hardware VM) | Yes | Prod with minimal overhead |

For production agents executing untrusted code: use `kata-fc`. Firecracker's <125ms boot and ~5MB memory overhead per microVM makes warm pools economically viable at scale.

### Lifecycle controls

```bash
# Pause an agent mid-task (e.g., for checkpointing or audit)
kubectl pause sandbox my-agent

# Resume
kubectl resume sandbox my-agent

# Delete — controller cleans up all child resources (PVC, Service, etc.)
kubectl delete sandbox my-agent
```

Pause/resume is critical for agents doing long-running tasks that need human review checkpoints or cost-saving during off-peak hours.

## Receipt

> Receipt pending — July 1, 2026

## See also
- [F-06 · Agent Sandboxing](f06-agent-sandboxing.md) — isolation tier decision framework (microVM vs gVisor vs hardened containers)
- [F-182 · MCP Server CVE Supply Chain Exploits](f182-mcp-server-cve-supply-chain-exploits.md) — why sandbox boundaries matter for tool servers
- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — multi-agent topology that benefits from stable per-agent sandbox identity
