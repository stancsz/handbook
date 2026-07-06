# S-599 · The Reasoning-Execution Boundary

When your AI agent can be manipulated into doing something harmful, the problem isn't the prompt. It's that the same system that decides *what* to do also *does* it — on the same substrate, behind the same firewall, with the same privileges. The reasoning-execution boundary pattern (from the Parallax framework, arXiv:2604.12986) separates these two concerns architecturally: the thinker never holds the keys, the doer never sees the reasoning.

## Forces

- **Prompt guardrails fail because they share a substrate with attacks.** A prompt injection payload that reaches the LLM runs through the exact same computational path as the safety instructions. If you can corrupt the input, you can bias the output — guardrail and attack compete on the same ground.
- **Cross-agent propagation compounds the problem.** In multi-agent systems, the output of one agent becomes the input to another. A single successful injection propagates to 48% of co-running agents (Gravitee 2026, 750 orgs). Trust between agents becomes an attack surface.
- **Governance needs structural enforcement, not behavioral trust.** When agents cross organizational boundaries or handle sensitive operations, you cannot audit intent — you must audit capability. The question is not "did the agent intend to follow policy?" but "was the agent structurally unable to violate it?"

## The move

Split the agent into two distinct processes on separate infrastructure:

**The Thinker** — a reasoning-only model with no tool access, no file I/O, no network egress. It outputs structured decision objects (action, target, parameters, confidence, justification). It never executes.

**The Executor** — a separate, constrained runtime that receives decision objects from the Thinker and executes them. The Executor enforces a capability allowlist: it can only perform actions enumerated in its policy. The Thinker's output is advisory; the Executor's policy is authoritative.

```
┌─────────────────────────────────────────────────────┐
│  Thinker (reasoning-only, no privileged access)     │
│  ┌─────────────────────────────────────────────┐   │
│  │ Prompt + context → reasoning model          │   │
│  │ Output: Decision object                     │   │
│  │   { action, target, params, confidence }   │   │
│  └──────────┬──────────────────────────────────┘   │
│             │ decision object (structured JSON)    │
│             ▼                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  Executor Policy (capability allowlist)       │  │
│  │  "Can this action be performed? By whom?"     │  │
│  └──────────┬──────────────────────────────────┘  │
│             │ approved action                      │
│             ▼                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  Executor (action runtime, no reasoning)     │  │
│  │  Tool calls, file I/O, network requests      │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Implementing the boundary in Python

```python
from dataclasses import dataclass
from typing import Literal
import hashlib

@dataclass
class DecisionObject:
    action: str
    target: str
    params: dict
    confidence: float
    justification: str
    thinker_id: str
    signature: str  # HMAC of the decision by the Thinker

class ExecutorPolicy:
    """Capability allowlist — the single source of truth for what can execute."""
    def __init__(self, allowed_actions: dict[str, list[str]]):
        # Map action types → allowed targets/parameters
        self.allowed = allowed_actions

    def can_execute(self, decision: DecisionObject) -> tuple[bool, str]:
        """Returns (allowed, reason). The only gate that matters."""
        if decision.action not in self.allowed:
            return False, f"Action '{decision.action}' not in allowlist"
        if decision.target not in self.allowed[decision.action]:
            return False, f"Target '{decision.target}' not permitted for {decision.action}"
        if decision.confidence < 0.85:
            return False, f"Confidence {decision.confidence:.2f} below threshold 0.85"
        return True, "Approved"

    def execute(self, decision: DecisionObject) -> dict:
        # In production: enforce timeout, sandbox, audit log
        # The Executor has NO access to the Thinker's prompt or context
        if decision.action == "send_email":
            return {"status": "sent", "to": decision.target}
        elif decision.action == "read_file":
            return {"status": "ok", "content": "[file content redacted]"}
        return {"status": "noop"}
```

### Key invariants

1. **Thinker is reasoning-only.** No `tools` parameter in the API call. If the model cannot call tools, an injected payload cannot either — it can only influence the reasoning output.
2. **Decision objects are signed.** The Thinker HMAC-signs every decision. The Executor verifies before executing. This prevents injection of fake decisions into the executor queue.
3. **Executor policy is the only gate.** The Thinker's "confidence" score is advisory. The Executor's allowlist is the authoritative boundary. No amount of confident reasoning unlocks a prohibited action.
4. **Cross-agent decisions require multi-sig.** When a decision from Agent A feeds into Agent B's workflow, both Thinker signatures must verify before the Executor acts.

### Why not just prompt guardrails?

Prompt guardrails have three structural weaknesses that architectural separation eliminates:

| Weakness | Guardrail | Structural Boundary |
|----------|-----------|--------------------|
| Same substrate as attack | Injection and guardrail compete on same model | Thinker is tool-free; Executor is policy-gated |
| Context window contamination | Long sessions degrade guardrail quality | Thinker has no persistent privileged state |
| Cross-agent propagation | Trust compounds across hops | Each hop requires new Executor policy check |

## Receipt

> Verified 2026-07-05 — arXiv:2604.12986 (Parallax, Fokou, Apr 2026): default configuration across 280 adversarial test cases blocks 98.9% of attacks with zero false positives. Key architectural insight confirmed: structural separation outperforms prompt-level defenses by treating the think/act boundary as an infrastructure concern, not a content concern.

## See also

- [S-583 · The Agent Protocol Stack — MCP, A2A, and Where the Boundary Lives](s583-the-agent-protocol-stack-mcp-a2a-and-where-the-boundary-lives.md) — protocol-layer boundaries between agents
- [S-598 · The Multi-Agent Overcommit](s598-the-multi-agent-overcommit.md) — when more agents compounds, not solves, the problem
- [I-010 · Agentic Prompt Injection: Defense-in-Depth for Production](s375-agentic-prompt-injection-defense-in-depth-for-production.md) — prompt-level defenses; structural separation is the complement, not replacement
- [S-591 · Agent Non-Human Identity Governance](s591-agent-non-human-identity-governance.md) — the identity model that makes signed decisions tractable
