# F-180 · AI Incident Commander

Your pager fires at 2 AM. Latency is normal. Error rate is 0.1%. Throughput is fine. Users are already complaining on Slack that your agent is giving confidently wrong answers. Your SRE runbook has nothing on this. Standard on-call tooling shows green. The model is returning 200 OK while quietly damaging user trust. This is the failure mode that standard runbooks are structurally blind to — and it is now the most common AI incident type in production.

The fix is a dedicated AI incident response discipline: a four-layer diagnostic tree, versioned AI artifact primitives, and an incident commander who owns the full stack from detection through regression verification.

## Forces

- **Standard SRE runbooks assume error = failure.** An LLM returning a confidently wrong answer looks identical to a correct one from every traditional monitoring signal. The gap between "system healthy" and "model degraded" can last hours — discovered by users, not dashboards
- **Four failure layers, one symptom.** Provider model changes, prompt instruction drift, retrieval corpus degradation, and tool API breakage all produce the same user-facing symptom: bad output. The correct mitigation for each is completely different — applying the wrong one wastes critical incident time
- **Blameless postmortems scatter across four teams.** ML platform owns the model layer. Product engineering owns the prompt. Data owns retrieval. Infrastructure owns tools. When a prompt change interacted with a retrieval schema change to produce a novel failure, nobody's postmortem covers both
- **The fastest containment levers are the least instrumented.** Prompt rollback (sub-minute) and model pinning (also fast) require version control and feature flags that most teams haven't built. The fallback — a full code deploy — takes 15+ minutes during an incident

## The move

### 1. The four-layer diagnostic tree

Every AI incident roots to one of four layers. Identify before you act:

| Layer | What breaks | Fastest mitigation |
|---|---|---|
| **Model** | Provider version change, hardware error, reward hacking | Pin model version, rollback to last known-good alias |
| **Prompt** | Instruction drift, output format change, constraint decay | Roll back prompt template, redeploy without code deploy |
| **Retrieval** | Knowledge gap, schema drift, ranking regression, stale index | Refresh index, disable RAG, fall back to base model |
| **Application** | Tool API failure, guardrail misfire, downstream system bug | Disable tool via feature flag, circuit-break the tool |

The single most time-wasting behavior during an AI incident is changing multiple layers simultaneously. Pick one layer to investigate first: start at the layer closest to the user output (Prompt → Retrieval → Model → Application) and move outward.

### 2. Version control for AI artifacts

Your on-call engineer cannot roll back a prompt they cannot find. Treat these as first-class versioned artifacts:

```python
# ai_incident_primitives.py
# Core incident response primitives for LLM/agent systems

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib


class AILayer(Enum):
    MODEL = "model"
    PROMPT = "prompt"
    RETRIEVAL = "retrieval"
    APPLICATION = "application"


@dataclass
class AIArtifact:
    name: str
    layer: AILayer
    content: str
    version: str
    deployed_at: datetime
    deployed_by: str
    git_sha: Optional[str] = None

    def rollback_hash(self) -> str:
        """Content hash for regression comparison post-rollback."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:12]


class AIActifactRegistry:
    """Versioned registry for all AI artifacts — prompts, model configs,
    retrieval schemas, tool definitions. On-call engineers roll back through
    this, not through git history or Confluence."""

    def __init__(self):
        self.artifacts: dict[str, list[AIArtifact]] = {}

    def deploy(
        self,
        name: str,
        layer: AILayer,
        content: str,
        deployed_by: str,
        git_sha: Optional[str] = None,
    ) -> str:
        version = f"{name}-v{datetime.utcnow():%Y%m%d%H%M%S}"
        artifact = AIArtifact(
            name=name, layer=layer, content=content,
            version=version, deployed_at=datetime.utcnow(),
            deployed_by=deployed_by, git_sha=git_sha,
        )
        self.artifacts.setdefault(name, []).append(artifact)
        return version

    def rollback(self, name: str, target_version: Optional[str] = None) -> AIArtifact:
        """Roll back to previous version (or specific target). Returns artifact."""
        history = self.artifacts.get(name, [])
        if len(history) < 2:
            raise ValueError(f"No rollback target for {name} — only {len(history)} version(s)")
        target = (
            next(a for a in reversed(history) if a.version == target_version)
            if target_version
            else history[-2]
        )
        # Deploy as new version with rollback marker
        rollback_marker = f"rollback-to-{target.version}"
        return self.deploy(
            name=name,
            layer=target.layer,
            content=target.content,
            deployed_by="incident-rollback",
        )

    def diff(self, name: str, v1: str, v2: str) -> list[str]:
        """Line-level diff between two versions of the same artifact."""
        a1 = next((a for a in self.artifacts.get(name, []) if a.version == v1), None)
        a2 = next((a for a in self.artifacts.get(name, []) if a.version == v2), None)
        if not a1 or not a2:
            raise ValueError(f"Version not found: {v1} or {v2}")
        lines1, lines2 = a1.content.splitlines(), a2.content.splitlines()
        diff = []
        for i, (l1, l2) in enumerate(zip(lines1, lines2)):
            if l1 != l2:
                diff.append(f"- line {i+1}: {l1}")
                diff.append(f"+ line {i+1}: {l2}")
        if len(lines1) != len(lines2):
            diff.append(f"[content length changed: {len(lines1)} → {len(lines2)} lines]")
        return diff


class FeatureFlag:
    """Kill switch for AI features. Every agent tool and capability needs one."""

    def __init__(self):
        self._flags: dict[str, bool] = {}

    def enable(self, feature: str):
        self._flags[feature] = True

    def disable(self, feature: str):
        self._flags[feature] = False

    def is_enabled(self, feature: str) -> bool:
        return self._flags.get(feature, True)

    def disable_multiple(self, features: list[str]):
        for f in features:
            self.disable(f)


# Incident response workflow using the primitives above
def run_ai_incident_diagnosis(
    registry: AIActifactRegistry,
    flags: FeatureFlag,
    concern: str,  # e.g., "agent returning hallucinated URLs in tool calls"
) -> AILayer:
    """
    Four-layer diagnostic tree for AI incidents.
    Returns the root layer so the commander knows where to act.
    """
    print(f"[INCIDENT] User concern: {concern}")
    print("[INCIDENT] Running four-layer diagnostic...")

    # Layer 1: Check application (tools, guardrails, downstream)
    # — Is the tool API responding? Are guardrails firing unexpectedly?
    print("[DIAG] Layer 4 (Application): checking tool API health...")
    # (Real impl: call health endpoints, check guardrail logs)
    app_healthy = True  # placeholder
    if not app_healthy:
        print("[DIAG] → Application layer: tool API failure detected")
        flags.disable("agent_external_tools")
        return AILayer.APPLICATION

    # Layer 2: Check retrieval (RAG, knowledge index)
    print("[DIAG] Layer 3 (Retrieval): running golden query set against RAG...")
    # (Real impl: run holdout queries, compare recall against baseline)
    retrieval_ok = True  # placeholder
    if not retrieval_ok:
        print("[DIAG] → Retrieval layer: recall regression detected")
        flags.disable("rag_augmentation")
        return AILayer.RETRIEVAL

    # Layer 3: Check prompt (instruction drift, constraint decay)
    print("[DIAG] Layer 2 (Prompt): comparing current vs. baseline output on golden set...")
    # (Real impl: run golden dataset, compute pass rate delta)
    prompt_ok = True  # placeholder
    if not prompt_ok:
        print("[DIAG] → Prompt layer: regression detected, initiating rollback")
        rollback_artifact = registry.rollback("agent_system_prompt")
        print(f"[ROLLBACK] Rolled back to {rollback_artifact.version}")
        return AILayer.PROMPT

    # Layer 4: Check model (provider change, version regression)
    print("[DIAG] Layer 1 (Model): checking provider version and output distribution...")
    # (Real impl: compare output embeddings, check provider changelog)
    print("[DIAG] → Model layer: provider-side regression suspected")
    print("[CONTAINMENT] Pin model to last known-good version via provider alias")
    return AILayer.MODEL
```

### 3. Incident commander responsibilities

The AI incident commander is not an ML engineer or an SRE — it is a role that coordinates the four-layer diagnostic across teams that each own one layer:

1. **Triage:** Route the incident to the correct layer using the diagnostic tree
2. **Contain:** Apply the fastest appropriate containment (prompt rollback → model pin → feature flag → traffic split)
3. **Verify:** Run golden dataset regression before declaring the incident resolved
4. **Blameless postmortem:** Write the postmortem with explicit layer attribution so the fix lands in the right team's ownership
5. **Feedback:** Update the golden dataset or runbook if the incident revealed a coverage gap

The commander does not need to know how to fix each layer — they need to know which team owns which layer and how to route containment steps to the right owner fast.

### 4. Severity grading for AI incidents

| Severity | User impact | Detection | Response SLA |
|---|---|---|---|
| **SEV-1** | Users receiving actively harmful outputs | Minutes (user complaint or eval signal) | 15-min containment, 4-hr root cause |
| **SEV-2** | Degraded quality, no harm | Hours (golden dataset regression) | 1-hr containment, 24-hr root cause |
| **SEV-3** | Silent regression, no user notice | Days–weeks (periodic eval) | Next sprint |

SEV-1 is the only one that warrants waking someone up. SEV-2 is managed through golden dataset monitoring. SEV-3 is closed through the improvement loop.

## Receipt

> Receipt pending — June 30, 2026
> The code above is a structural reference implementation. The four-layer diagnostic tree and AI artifact registry primitives reflect real production patterns documented in industry postmortems (Tian Pan, April 2026; AppScale, May 2026; AIUC-1 Consortium, March 2026). The `FeatureFlag` and `AIActifactRegistry` classes are archetypal — actual implementations vary by stack (LangSmith for tracing, Pydantic + feature flags for kill switches, OpenTelemetry for distributed traces). Full end-to-end execution requires a live agent stack and a pre-built golden dataset, which this run did not have access to. Build and validate against your own stack before relying on it in an incident.

## See also

- [F-176 · Agent Runbook-Driven Reliability](f176-agent-runbook-driven-reliability.md) — treating runbooks as first-class agent code
- [F-171 · Agent Drift Detection](f171-agent-drift-detection.md) — detecting behavioral regressions before users notice
- [S-209 · Agent Production Observability](stacks/s209-agent-production-observability.md) — instrumenting the signals the diagnostic tree needs
- [S-230 · Agent Harness Engineering](stacks/s230-agent-harness-engineering-the-eval-layer-production-demands.md) — building the eval infrastructure that feeds the golden dataset
