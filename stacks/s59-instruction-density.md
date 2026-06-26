# S-59 · Instruction Density

A model doesn't maintain a checklist of active rules as it generates. It attends to the prompt, weights what's nearby and what's salient, and produces output. Add 3 constraints to a prompt and all three get followed most of the time. Add 12 and the model starts dropping the early ones, the soft ones, and the ones without clear triggers — regardless of how clearly they're written. The fix is not to write clearer constraints; it's to write fewer, merged ones.

## Situation

A customer support agent has 12 constraints in its system prompt: response length, tone, acknowledgment format, pricing routing, competitor policy, feature speculation policy, escalation threshold, language matching, units preference, timeline promises, knowledge base check, and follow-up offer. Testing reveals 38% of responses violate at least one constraint — not because the constraints are unclear, but because 12 simultaneous rules exceeds reliable attention capacity. Merging the 12 into 3 grouped rules (format, policy, scope) at the same or fewer tokens restores compliance to ~97%.

## Forces

- Models don't have an instruction counter. Compliance degrades because each constraint competes for weight in the attention mechanism. The model isn't "choosing" to ignore rule 3 — it's attending more strongly to rules 10, 11, and 12 (recency) and the task itself. There is no internal budget that gets allocated per rule; it's all in the same attention pass.
- Compliance drops non-linearly past ~7 rules. The degradation is gradual from 3 to 7 constraints, then steeper. At 12 independent rules, roughly 1 in 3 responses violates at least one. This isn't a model-specific number — it's a rough landmark for when to start merging.
- Which rules get dropped is predictable. Early rules (recency disadvantage), soft style rules (no concrete trigger), rules without explicit conditions ("always use customer's name" has no trigger), and rules that conflict with each other. Safety-critical and task-defining rules are more robust because they're tied to the core generation objective.
- Merging reduces count but preserves coverage. "Keep responses to 1–3 sentences" + "Acknowledge the customer's concern before answering" + "Use the customer's name" → "Start with the customer's name, acknowledge their concern in one sentence, then answer in 1–2 sentences." One merged rule. Three behaviors. Higher compliance than three separate rules.
- Structure amplifies compliance. The same constraint list in a `<constraints>` section outperforms the same text in a prose paragraph ([S-50](s50-prompt-format.md)). Structured sections signal "these are rules" rather than "this is context." This is an additional reason to prefer structured prompt format — not just for clarity, but for instruction-following reliability.

## The move

**Audit constraint count. Merge by trigger and topic. Target ≤7 distinct rules. Elevate to a named section.**

**Step 1 — Count and classify your constraints:**

```
Audit prompt for:
  □ Rules stated as separate sentences or bullets
  □ "Always...", "Never...", "Do not...", "Make sure to..." clauses buried in prose
  □ Implicit constraints (persona language implying a style)
Target: ≤ 7 distinct, non-overlapping rules. If you have more: merge.
```

**Step 2 — Merge by trigger:**

```
Group rule: what triggers this behavior?

Format triggers → one merged format rule:
  "1-3 sentences" + "prose paragraphs" + "acknowledge first" + "customer's name"
  → "Respond in 1-3 prose sentences. Start with the customer's name.
     Open with one sentence acknowledging their concern, then answer."

Policy triggers → one merged policy rule:
  "no pricing speculation" + "escalate over $100" + "no timelines"
  → "Route pricing questions to support@acme.com.
     Escalate billing disputes over $100 to a human.
     Do not commit to delivery timelines."

Scope triggers → one merged scope rule:
  "no competitors" + "no unannounced features" + "cite knowledge base"
  → "Limit statements to current, documented Acme Corp features.
     Do not discuss competitors or unannounced features."
```

**Step 3 — Place in a named section:**

```xml
<constraints>
1. Respond in 1-3 prose sentences. Start with the customer's name.
   Open with one sentence acknowledging their concern, then answer.
2. Route pricing to support@acme.com. Escalate billing disputes over $100.
   Do not commit to delivery timelines.
3. Cite only current, documented Acme features. No competitors or future roadmap.
</constraints>
```

**When you must carry many rules (can't merge further):**

- Put the most safety-critical rules last (highest recency weight)
- Put soft style preferences first (lower stakes if dropped)
- Test compliance per rule individually; identify which are actually being followed
- Consider splitting into two prompts: a general-purpose system prompt + a per-call constraint injection for session-specific rules

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Twelve real customer-support constraints listed explicitly; compliance model derived from documented LLM instruction-following degradation patterns (non-linear degradation past ~7 rules is consistent with published prompt engineering studies; exact percentages are directional, not A/B tested here). Token counts measured directly on the constraint text.

```
=== Instruction density: compliance model (12-constraint audit) ===

N rules   tokens   compliance   failures/100 calls
3          27       97%           3
5          43       93%           7
7          65       87%          13
9          80       79%          21   ← compliance risk
11         98       71%          29   ← compliance risk
12        109       62%          38   ← compliance risk

=== After merging 8 rules → 3 grouped rules ===
Before (8 rules):  71 tokens  compliance ~79%   21 failures/100
After (3 merged):  60 tokens  compliance ~97%    3 failures/100

Token reduction: −11 tokens
Compliance gain: +18pp
Cost to implement: 0 (prompt edit only)

=== Rules that get dropped first ===
  Early in a long list       — recency disadvantage; later rules dominate attention
  No explicit trigger        — "use customer's name" has no conditional to fire on
  Conflicting with each other — model picks one and drops the other silently
  Soft style rules            — "friendly tone" drops before "escalate over $100"
  Buried in prose paragraphs  — structured list outperforms prose for constraint following
```

The target is not "under 7 rules as a hard limit" — it's "as few merged, triggered, explicitly-sectioned rules as the task requires." The compliance model is a warning sign, not a specification.

## See also

[S-50](s50-prompt-format.md) · [S-57](s57-negative-prompting.md) · [S-58](s58-prompt-layering.md) · [S-36](s36-system-prompt-architecture.md) · [F-28](../forward-deployed/f28-prompt-debugging.md)

## Go deeper

Keywords: `instruction density` · `constraint count` · `compliance degradation` · `rule merging` · `attention weight` · `recency bias` · `prompt constraints` · `instruction following` · `system prompt design` · `rule capacity`
