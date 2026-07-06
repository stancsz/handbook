# S-206 · Context Debt

You shipped the agent. Demos were clean. Two weeks in production, it started making wrong decisions on a specific customer segment — the one with non-standard data formats. You tweak the prompt. It gets worse on another segment. You revert. The agent is "working" — returning 200s, calling tools, producing output. The failure is invisible because nobody has defined what the right output looks like for 80% of the real data. This is context debt: the accumulated gap between what the agent infers from your data and what your business actually means. It builds silently during development, passes undetected through testing, and compounds in production.

## Forces

- Two teams ship identical agents with identical prompts, identical frameworks, identical tool configs. They get completely different production outcomes. The variable is almost never in the post-mortem.
- Smarter models amplify context debt, not cancel it — a more capable model makes wrong decisions faster and with more confidence.
- >40% of agentic AI projects will be cancelled by end of 2027 (Gartner 2025); ~95% of enterprise GenAI pilots delivered no measurable P&L impact (MIT NANDA 2025). The #1 stated barriers are hallucination, poor prompts, memory gaps — these are symptoms. The root cause is context debt.
- Context debt is invisible in development: test data is clean, bounded, and matches the happy path. Production data is messy, multi-format, and the agent handles it by defaulting to plausible-sounding assumptions.
- Fixing context debt is cheaper than switching models. Teams keep buying the next model hoping the new one will "just get it." It won't — the problem is in the data contract, not the model.
- The debt accrues across three layers: schema assumptions (what fields mean), business rules (what outcomes are correct), and domain vocabulary (which term means what in your org).

## The move

**Context debt lives in three layers. Fix them in order.**

### Layer 1 — Schema Debt

The agent assumes a data schema that doesn't match production reality.

Symptoms: correct behavior on one data format, silent wrong outputs on others, field names that look right but carry wrong values.

Diagnosis:
```
1. Run the agent against a random production sample (not test data)
2. Log every data field the agent reads
3. Compare against the documented schema
4. Find: missing fields, fields with wrong names, fields with mixed types
```

Fix: Write a data contract — a explicit schema the agent trusts, with a fallback that flags unexpected shapes instead of guessing.

```python
def parse_record(raw: dict) -> ValidatedRecord:
    """Parse a record, explicitly failing on schema mismatch."""
    required = {"customer_id", "amount", "currency", "date"}
    present = set(raw.keys())
    missing = required - present
    unexpected = present - required

    if missing:
        # Don't guess. Flag. Context debt discovered here.
        raise RecordSchemaError(f"Missing fields: {missing}, unexpected: {unexpected}")

    # Explicit coercion with known-good defaults
    return ValidatedRecord(
        customer_id=str(raw["customer_id"]),
        amount=float(raw["amount"]),
        currency=raw["currency"].upper(),
        date=parse_date(raw["date"]),
    )
```

### Layer 2 — Business Rule Debt

The agent assumes outcomes without an explicit rule definition.

Symptoms: correct on happy path, wrong on edge cases, different wrong answers on different edge cases.

Diagnosis:
```
1. Collect every production failure for 2 weeks
2. Classify by: was it a bad decision, or a missing/inconsistent data?
3. For bad decisions: what business rule did the agent violate?
4. For data issues: what would the right answer have been with the right data?
```

Fix: For every agent decision, write a decision audit log that captures the input state, the inferred context, and the chosen action. Without this, you can't distinguish "agent made a bad call" from "agent was given bad data."

```python
@dataclass
class DecisionAuditEntry:
    timestamp: datetime
    input_summary: str        # hashed PII, logged for debugging
    inferred_context: dict    # what the agent "knew" at decision time
    action_taken: str
    outcome: str               # confirmed, wrong, unknown

    # Critical field most teams skip:
    data_quality_score: float  # 0-1: how complete/correct was input data?

def audit_decision(agent_output, input_record, outcome):
    entry = DecisionAuditEntry(
        timestamp=datetime.utcnow(),
        input_summary=hash_record(input_record),
        inferred_context={
            "amount_parsed": agent_output.get("amount"),
            "currency_assumed": agent_output.get("currency"),
            "data_quality_score": score_record_completeness(input_record),
        },
        action_taken=agent_output.get("action"),
        outcome=outcome,
        data_quality_score=score_record_completeness(input_record),
    )
    # Write to audit table, partition by data_quality_score
    # Low score + wrong outcome = context debt, not agent failure
```

### Layer 3 — Vocabulary Debt

The agent uses the wrong term, causing wrong tool calls or wrong queries.

Symptoms: agent queries the wrong system, calls the wrong tool, or retrieves irrelevant context because your domain uses "account" to mean three different things in three different systems.

Fix: Build an explicit vocabulary bridge — a glossary the agent reads at session start, mapping ambiguous terms to system-specific identifiers.

```python
VOCABULARY_BRIDGE = {
    "account": {
        "crm": "Contact.AccountId",
        "billing": "Invoice.AccountNumber",
        "support": "Ticket.AccountId",
        # Agent must qualify: which account?
        "ambiguous_action": "BLOCK",
    },
    "balance": {
        "financial": "AccountLedger.CurrentBalance",
        "usage": "MeterReading.Balance",
        "credit": "CustomerCreditLimit.Remaining",
        "ambiguous_action": "ASK_USER",
    },
}

SYSTEM_PROMPT_FRAGMENT = f"""
DOMAIN VOCABULARY (read carefully — wrong term = wrong system):
{json.dumps(VOCABULARY_BRIDGE, indent=2)}

Rule: if your query references an ambiguous term, you MUST qualify it
with the system prefix. "account" alone is not enough — say "account.crm".
"""
```

**The governing equation:**
> **Ungoverned Context × Agent Autonomy = Increased Risk Exposure**

Reduce either side. The cheaper lever is context governance — fix the data contract, the audit log, and the vocabulary bridge before you try a bigger model.

## Receipt

> Receipt pending — June 29, 2026

## See also

- [S-13 · Context Engineering](s13-context-engineering.md) — the broader discipline of curating the right tokens
- [S-21 · Context Compaction](s21-context-compaction.md) — managing context as sessions grow
- [F-171 · Agent Drift Detection](forward-deployed/f171-agent-drift-detection.md) — detecting when behavior slowly diverges from intent
- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — recovering from failures; context debt often surfaces as a healable failure
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — Lusser's Law and the compounding cost of multi-step failure
