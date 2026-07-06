# S-327 · LLM Noisy-Neighbor Scheduling: When One Tenant Triples Everyone's Latency

Your dashboards show 200s. P50 latency is 800ms. But P95 has silently tripled to 4.2 seconds, and three enterprise customers are drafting escalation emails. Nothing is broken — one tenant is running 200K-token research queries on shared vLLM infrastructure, and traditional multi-tenant isolation (rate limits, token budgets, namespace isolation) had no answer for variable-length context consumption on a shared GPU KV cache. This is the LLM noisy-neighbor problem at the scheduling layer, and it requires controls that don't exist in standard cloud infrastructure.

## Forces

- **KV cache is a fixed, shared resource.** Unlike stateless HTTP requests, LLM inference allocates GPU memory proportional to context length. A 2K-token query and a 200K-token query occupy vastly different memory footprints simultaneously. The KV cache is first-come-first-served — there's no queue for GPU memory.
- **Traditional rate limits measure requests/second, not compute.** A tenant sending 10 short queries and a tenant sending 1 long query can both stay within a 10 req/sec limit. The long-query tenant consumes 50× more GPU memory and blocks the batch scheduler for the entire sequence length.
- **Preemption in LLM serving is non-trivial.** Traditional OS preemption doesn't apply. Once a sequence has begun, you can't pause it mid-compute without discarding the KV cache state and wasting all compute already spent. You can only drop it (wasteful) or wait.
- **Speculative decoding amplifies the problem.** When a shared cluster uses speculative decoding, the draft model and the verify model both consume GPU memory. A long-context tenant can exhaust the KV cache budget needed for speculative verification on short-context requests from other tenants.
- **P50 hides P95.** Average latency looks fine. The long-context tenant's 45-second inference time gets averaged down by all the 500ms requests. You don't see the problem until P95 is already on fire.

## The move

Three interlocking controls at the serving layer — none of them sufficient alone:

### 1. Context-length scheduling (sort-first batching)

Instead of FIFO batching, sort incoming requests by context length and batch similar lengths together. This prevents a 200K-token request from blocking 50 short requests in the same iteration.

```python
# Simplified sort-first batching logic
from collections import defaultdict

def batch_by_context_length(pending_requests, max_batch=8):
    # Group requests by approximate context length bucket
    buckets = defaultdict(list)
    for req in pending_requests:
        bucket = bucket_for(req.prompt_tokens)
        buckets[bucket].append(req)

    batches = []
    for bucket in sorted(buckets.keys()):
        # Short-first scheduling: process low-context requests first
        # so they don't wait behind long-context requests
        requests = buckets[bucket][:max_batch]
        batches.append(requests)
    return batches

def bucket_for(token_count):
    """Map token count to scheduling bucket."""
    if token_count <= 2048:
        return 0   # short
    elif token_count <= 8192:
        return 1   # medium
    elif token_count <= 32768:
        return 2   # long
    else:
        return 3   # very long — isolate or deprioritize

# vLLM scheduler_config options that enable this:
# "policy": "fcfs"  # change to sort by input length
# Set max_model_len to enforce hard ceiling per request
```

vLLM's scheduler supports this via the `policy` parameter. Set `max_model_len` to enforce a hard per-request ceiling and prevent a single tenant from claiming the entire context window.

### 2. Per-tenant KV cache partitioning

Allocate a hard ceiling of KV cache memory per tenant. When a tenant's cache partition is full, new requests from that tenant queue — they wait for the cache to be freed as prior requests complete.

```yaml
# kubernetes/vllm-config.yaml — per-tenant cache allocation
# vLLM doesn't natively support this as of v0.6.x, so enforce at the gateway layer
scheduler_config:
  max_model_len: 131072          # global ceiling (128K)
  max_num_batched_tokens: 8192   # max tokens per forward pass

# Enforce per-tenant ceilings via the inference gateway (e.g., vLLM-compatible proxy)
tenant_limits:
  enterprise_acme:
    max_context_tokens: 32768     # 32K ceiling for this tenant
    max_concurrent_requests: 8    # prevent request pile-up
    priority: high
  pro_tenant:
    max_context_tokens: 16384     # 16K ceiling
    max_concurrent_requests: 4
    priority: normal
  free_tier:
    max_context_tokens: 4096      # aggressive cap
    max_concurrent_requests: 2
    priority: low                  # scheduled last in equal-bucket situations
```

The key insight: KV cache partitions are freed asynchronously as sequences complete. Long-context requests hold their partition for the full generation time, which can be 30–120 seconds. A tenant with one long-running request can hold 30% of GPU memory for a minute while other tenants queue.

### 3. Backpressure and queue-depth alerts

Route backpressure at the gateway before requests reach the GPU. Measure queue depth per tenant and reject or queue early rather than letting requests pile up behind a long-context tenant.

```python
import time
from dataclasses import dataclass
from collections import deque

@dataclass
class TenantQueue:
    tenant_id: str
    requests: deque
    max_depth: int
    max_wait_seconds: float

class LLMSchedulingGateway:
    def __init__(self):
        self.tenant_queues: dict[str, TenantQueue] = {}
        self.global_queue: deque = deque()
        self.running: dict[int, dict] = {}  # request_id -> metadata

    def enqueue(self, tenant_id: str, request: dict) -> str | None:
        """Enqueue request. Returns request_id or None if tenant is over limit."""
        queue = self.tenant_queues.get(tenant_id)
        if queue and len(queue.requests) >= queue.max_depth:
            # Hard limit hit — reject or spill to overflow queue
            self.enqueue_overflow(tenant_id, request)
            return None

        request_id = f"{tenant_id}_{time.time_ns()}"
        request["id"] = request_id
        request["enqueued_at"] = time.monotonic()
        self.global_queue.append(request)
        return request_id

    def dequeue_batch(self, max_tokens: int) -> list[dict]:
        """Pull next batch respecting context-length bucketing and priority."""
        batch = []
        batch_tokens = 0

        # Sort global queue by priority then context length (short first)
        sorted_reqs = sorted(
            self.global_queue,
            key=lambda r: (-r.get("tenant_priority", 0), r["prompt_tokens"])
        )

        for req in sorted_reqs:
            tokens = req["prompt_tokens"] + req.get("max_tokens", 512)
            if batch_tokens + tokens > max_tokens:
                break
            batch.append(req)
            batch_tokens += tokens
            self.global_queue.remove(req)

        return batch

    def get_backpressure_signal(self, tenant_id: str) -> dict:
        """Return queue health metrics for alerting."""
        queue = self.tenant_queues.get(tenant_id)
        if not queue:
            return {"status": "ok"}

        depth = len(queue.requests)
        oldest_age = 0
        if queue.requests:
            oldest_age = time.monotonic() - queue.requests[0]["enqueued_at"]

        return {
            "tenant_id": tenant_id,
            "queue_depth": depth,
            "max_depth": queue.max_depth,
            "oldest_wait_seconds": oldest_age,
            "pressure": "high" if depth >= queue.max_depth else "normal",
        }

# Alert when backpressure_signal["pressure"] == "high" for 60+ seconds
# This is the leading indicator — before P95 latency spikes
```

The backpressure signal is your leading indicator, not GPU utilization. By the time GPU utilization hits 90%, P95 has already degraded. Queue depth per tenant tells you the problem is forming before it reaches the hardware.

### 4. Context-window fairness (the 80/20 rule)

Reserve a percentage of GPU memory for short-context requests. Treat long-context requests as best-effort when the cluster is busy.

```python
# Reserve 20% of KV cache for short-context requests
KV_CACHE_RESERVE_FRACTION = 0.20

def can_schedule_request(prompt_tokens: int, running_requests: list) -> bool:
    total_kv_cache_used = sum(r["context_length"] for r in running_requests)
    # Hard ceiling: never exceed 100% of cache
    # Soft ceiling: never let long-context push short-context out
    if prompt_tokens <= 4096:
        # Short-context request — reserve headroom
        headroom = total_kv_cache_used + prompt_tokens
        return headroom <= 0.95 * KV_CACHE_SIZE  # allow short contexts 5% margin
    else:
        # Long-context — only schedule if well below threshold
        headroom = total_kv_cache_used + prompt_tokens
        return headroom <= (1 - KV_CACHE_RESERVE_FRACTION) * KV_CACHE_SIZE
```

## Receipt

> Receipt pending — 2026-07-01
>
> The scheduling patterns above are composable primitives — sort-first batching and KV cache partitioning are available in vLLM 0.6.x; per-tenant backpressure and context-window fairness are implemented at the gateway layer. A full end-to-end run requires a multi-tenant vLLM cluster with competing workload profiles. This entry will be updated with benchmarks from a 3-tenant cluster competing on a shared H100 once the test environment is provisioned.

## See also

- [S-73 · Multi-Tenant AI Isolation](s73-multi-tenant-ai-isolation.md) — covers context, data, rate, and cost isolation surfaces; this entry extends the scheduling layer
- [S-89 · Per-Tenant Quota Distribution](s89-per-tenant-quota-distribution.md) — covers token-bucket quota distribution across tenants; this entry covers the serving-layer scheduling problem that quotas can't solve alone
- [S-208 · Per-Tenant LLM Cost Attribution](s208-per-tenant-llm-cost-attribution.md) — ties the cost impact of long-context scheduling to per-tenant billing
- [F-192 · Cost Velocity Circuit Breaker](forward-deployed/f192-cost-velocity-circuit-breaker.md) — cost-side companion: velocity detection that fires before the KV cache budget is consumed
