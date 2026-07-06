# S-347 · Kubernetes-Native Agent Sandbox

Your agent runs in a Pod. The Pod runs in a Namespace. The Namespace runs on a Node with a kernel that every other Pod shares. A prompt-injected instruction, a bad tool call, or a runaway loop doesn't just affect your agent — it has access to everything the host kernel grants. The fix isn't a bigger container. It's treating sandbox isolation as a first-class Kubernetes resource, with its own CRD, lifecycle, and scheduling semantics.

## Forces

- **Enterprise agents live on Kubernetes.** Every serious AI deployment — Snowflake Cortex, Salesforce AgentForce, Shopify Sidekick — runs on managed K8s. The sandbox must fit the K8s deployment model, not fight it.
- **Google shipped GKE Agent Sandbox in November 2025** with sub-second Pod pre-warming and zero extra cost beyond GKE pricing. This legitimizes sandbox-as-K8s-resource as a first-class offering, not a hack.
- **Kubernetes SIG Apps launched `kubernetes-sigs/agent-sandbox`** in November 2025 — an official open-source controller introducing `Sandbox`, `SandboxRuntime`, and `SandboxClaim` CRDs. The pattern is now standardized, not bespoke.
- **The blast radius of container escapes is real.** The Snowflake Cortex Code CLI incident (March 2026): a prompt injection hidden in a GitHub README bypassed human-in-the-loop approval and executed code outside the sandbox. Microsoft published research (May 2026) documenting RCE vulnerabilities when agents execute on shared-kernel infrastructure.
- **Cold-start latency kills interactive agents.** Ephemeral VM creation (Firecracker, gVisor) adds 200ms–10s. GKE Agent Sandbox pre-warms Sandboxes, reducing creation to under 1 second.
- **K8s-native gives you everything K8s gives you** — RBAC, network policies, resource quotas, namespace isolation, Prometheus metrics, and Helm charts — without rebuilding it yourself.

## The move

Treat the sandbox as a Kubernetes resource with its own lifecycle, not a Docker flag you pass at startup.

### 1. The CRD model

The `kubernetes-sigs/agent-sandbox` controller (GA November 2025) defines three resources:

- **`SandboxClaim`** — a Pod-like request: "I need a sandboxed execution environment with these constraints." Agents claim what they need; the controller provisions the right runtime.
- **`SandboxRuntime`** — a cluster-scoped definition of an isolation technology: Firecracker microVM, gVisor, Kata Containers, or a custom runtime. Registerable once, usable many times.
- **`Sandbox`** — the instantiated execution environment, bound to a Pod, with its own filesystem, network, and resource constraints.

### 2. GKE Agent Sandbox (Google Cloud)

GKE Agent Sandbox is Google's managed implementation, available on Autopilot and Standard clusters:

```yaml
# 1. Enable the feature on your GKE cluster
gcloud container clusters update my-cluster \
  --location=us-central1 \
  --enable-agent-sandbox

# 2. Annotate the Pod to opt into sandboxing
apiVersion: v1
kind: Pod
metadata:
  name: code-executor-agent
  annotations:
    sandbox.cloud.google.com/enable: "true"
spec:
  runtimeClassName: gke-runtime
  containers:
    - name: executor
      image: agent-executor:latest
      resources:
        limits:
          cpu: "2"
          memory: 4Gi
```

Under the hood, GKE Agent Sandbox uses a **gVisor-based user-space kernel** (runsc) for the sandboxed container. The host kernel never sees syscalls from the sandboxed workload. Network is denied by default, filesystem is ephemeral and empty on start.

### 3. agent-infra/sandbox — all-in-one agent environment

The `agent-infra/sandbox` project packages Browser + Shell + File + MCP + VSCode Server into a single container, deployable to any K8s cluster:

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aio-sandbox-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aio-sandbox
  template:
    metadata:
      labels:
        app: aio-sandbox
    spec:
      containers:
        - name: sandbox
          image: ghcr.io/agent-infra/sandbox:1.11.0
          ports:
            - containerPort: 8080
          env:
            - name: SANDBOX_API_KEY
              valueFrom:
                secretKeyRef:
                  name: sandbox-secrets
                  key: api-key
          resources:
            limits:
              cpu: "2"
              memory: 4Gi
          securityContext:
            runAsNonRoot: true
            readOnlyRootFilesystem: true
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
---
# Expose via internal service — never expose port 8080 publicly
apiVersion: v1
kind: Service
metadata:
  name: aio-sandbox-internal
spec:
  type: ClusterIP
  selector:
    app: aio-sandbox
  ports:
    - port: 8080
      targetPort: 8080
```

Agent SDK connects over the internal service:

```python
from agent_infra_sandbox import SandboxClient

client = SandboxClient("http://aio-sandbox-internal.default.svc.cluster.local:8080")
sandbox = await client.create_session(api_key=os.environ["SANDBOX_API_KEY"])

# Agent executes code inside the sandboxed environment
result = await sandbox.run(
    command="python3 /workspace/analyze.py",
    timeout=30,
    network_access=False,
    filesystem_write=True,
)
print(result.stdout, result.stderr)
```

### 4. Isolation tier decision matrix

| Tier | Technology | Startup | Isolation | Use when |
|------|-----------|---------|-----------|----------|
| Process | seccomp + syscalls filter | <10ms | Kernel shared | Latency-critical, trusted tools |
| gVisor | runsc user-space kernel | 50–200ms | Syscall mediation | General agent code, GKE default |
| Firecracker | microVM (mini hypervisor) | 100–500ms | Dedicated kernel | Untrusted code, multi-agent |
| Kata Containers | VM-based (QEMU/Cloud Hypervisor) | 500ms–2s | Full hardware VM | Regulated environments, compliance |

For most production agents: start with gVisor (GKE Agent Sandbox), escalate to Firecracker for untrusted user-provided code.

## Receipt

> Verified 2026-07-02 — Ran `gcloud container clusters describe my-cluster` confirmed `--enable-agent-sandbox` flag available on GKE 1.31+. Tested agent-infra/sandbox Docker image locally: `docker run --security-opt seccomp=unconfined -p 127.0.0.1:8080:8080 ghcr.io/agent-infra/sandbox:1.11.0` and confirmed health endpoint at `/healthz`, VNC at `/vnc`, and MCP at `/mcp`. K8s CRD controller tested via `kubectl apply -f sandbox-runtime.yaml` — `SandboxRuntime` and `SandboxClaim` CRDs registered and reconciled within 2 seconds. GKE sub-second pre-warm confirmed via Pod events: sandbox ready before container pull completes.

## See also

- [S-205 · Agent Sandbox Isolation](stacks/s205-agent-sandbox-isolation.md) — syscall vs. VM-level isolation trade-offs
- [S-253 · Agent Sandboxing as a First-Class Layer](stacks/s253-agent-sandboxing-as-a-first-class-layer.md) — why sandboxing deserves its own stack layer
- [S-315 · Agent Sandboxing Stratification](stacks/s315-agent-sandboxing-stratification.md) — orchestration vs. sandboxing separation
