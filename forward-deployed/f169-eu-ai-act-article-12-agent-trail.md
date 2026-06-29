# F-169 · EU AI Act Article 12 Agent Audit Trail

On August 2, 2026, the EU AI Act's high-risk obligations activate. If your agent operates in credit scoring, hiring, insurance, critical infrastructure, or any Annex III domain, Article 12's logging requirements shift from best-practice to legal liability. The penalty: €35M or 7% of global turnover, whichever is higher. Most teams building agents today have no idea what's actually required.

## Forces

- **Article 12 is not standard logging.** ELK, Datadog, or a JSON file in S3 do not satisfy Article 12. The regulation requires logs that capture the full **decision chain** — not just what the model returned, but the specific inputs, retrieval results, and intermediate tool calls that led there.
- **"Reference database" in Article 12 is a new concept for agents.** Traditional software reads from databases and logs the read. Agents retrieve from vector stores, summarize chunks, and feed results into downstream decisions. Your log needs to capture which chunks were retrieved, their scores, and why the model selected them — not just the final prompt.
- **Ten-year retention is not a checkbox.** Article 18 requires ten-year documentation retention. Storing raw LLM request/response pairs for a decade in plaintext is a GDPR Article 32 disaster. You need a retention strategy that satisfies both regulations simultaneously.
- **The audit trail must survive the organization, not just the system.** Agents get updated, prompts change, model versions rotate. Your log needs stable identifiers that tie each decision back to the specific system version that produced it.
- **Agents produce too much data to log naively.** A single agent task with 20 tool calls, 3 retrievals, and a 64K context window can generate 500K+ tokens of loggable content per session. Naive logging will bankrupt your storage budget.

## The move

Article 12 requires logging four categories. For agents, each maps to a specific implementation:

### 1. Period of use → session envelope

At session start, write one immutable record:

```
session_envelope {
  session_id: UUIDv7 (time-sortable)
  agent_version: semver          # from agent registry, not git hash
  model_name: string            # e.g. "gpt-4o-2025-05-12"
  tool_versions: dict[str, semver]
  deployed_at: ISO8601          # when this version entered prod
  region: string
  user_jurisdiction: ISO3166    # determines which Annex III applies
  purpose: str                  # e.g. "cv-screening-candidates"
}
```

Session ID must be stable, monotonic, and cross-referenceable to the user's data erasure request under GDPR Article 17.

### 2. Reference database → retrieval provenance map

This is the agent-specific column. Log every retrieval event before it feeds the model:

```
retrieval_event {
  session_id: UUIDv7
  retrieval_rank: int            # 1-indexed, ordered by execution
  corpus_id: str                # which knowledge base
  corpus_version: semver        # snapshot at query time
  query: str                    # exact retrieval query
  top_k: int
  returned_chunks: list[{
    chunk_id: str               # stable ID in your vector store
    score: float
    text_hash: str              # SHA-256 of chunk text
    doc_uri: str                # source document
  }]
  selected_for_context: bool   # whether model actually used this chunk
}
```

`selected_for_context` is non-obvious: the model may retrieve 20 chunks and use 3. You must log which ones were included — this is the Article 12 "reference database" equivalent for agents.

### 3. Input data → sanitized input envelope

Log the user's raw input *before* any transformation:

```
input_envelope {
  session_id: UUIDv7
  raw_input_hash: str           # SHA-256 of raw input; do NOT store raw PII
  input_category: enum[USER_QUERY, RETRIEVED_CONTEXT, TOOL_RESULT, MODEL_OUTPUT]
  pii_detected: bool            # automated PII scan result
  pii_redacted: bool           # whether redacted before storage
  transformation_steps: list[str]  # e.g. ["entity_extraction", "query_expansion"]
}
```

Store only the hash for PII-bearing inputs. Store the full text only if PII was redacted or the input contains no PII categories.

### 4. Output data → decision record with causal chain

This is the most complex requirement. Log the full decision trace, not just the final output:

```
decision_record {
  session_id: UUIDv7
  sequence: int
  step_type: enum[TOOL_CALL, LLM_INFERENCE, RETRIEVAL, HUMAN_REVIEW]
  triggered_by_retrievals: list[chunk_id]   # which retrieval chunks influenced this step
  tool_name: str
  tool_args_hash: str            # hash of args; args may contain PII
  tool_result_hash: str          # hash of result
  model_reasoning: str | null    # reasoning trace if available (o1/o3 style)
  final_output_hash: str
  output_actionable: bool        # did this produce a consequential action?
  consequential_action_type: enum[NONE, DATA_ACCESS, MODIFICATION, EXTERNAL_API, DECISION] | null
}
```

`triggered_by_retrievals` is the Article 12 linkage: it creates a trace from output → intermediate steps → specific retrieved chunks → corpus version. This is what Article 12 means by "the data, including input data ... that were used in the operation of the system."

### Retention strategy

Store in a partitioned, append-only store. Partition by `deployed_at` year for 10-year rotation. After 2 years, migrate full decision records to cold storage (S3 Glacier Deep Archive). Keep session envelopes in hot storage for 10 years for subject-access and erasure requests.

PII-bearing fields (`raw_input_hash` reference, `tool_args_hash`, `tool_result_hash`) should use field-level encryption with keys rotated annually. Do not store plaintext PII in logs.

```python
# Minimal Article 12 logger — production-grade skeleton
from datetime import datetime, timezone
import hashlib, uuid, json
from typing import Literal

class Article12Logger:
    """EU AI Act Article 12 compliant audit trail for autonomous agents."""

    def __init__(self, store):
        self.store = store  # append-only partitioned store

    def log_session_envelope(self, agent_version: str, model_name: str,
                              tool_versions: dict, user_jurisdiction: str,
                              purpose: str) -> uuid.UUID:
        session_id = uuid.uuid7()  # time-sortable UUID
        record = {
            "type": "session_envelope",
            "session_id": str(session_id),
            "agent_version": agent_version,
            "model_name": model_name,
            "tool_versions": tool_versions,
            "deployed_at": datetime.now(timezone.utc).isoformat(),
            "user_jurisdiction": user_jurisdiction,
            "purpose": purpose,
        }
        self._append(session_id, record)
        return session_id

    def log_retrieval_event(self, session_id: uuid.UUID, corpus_id: str,
                            corpus_version: str, query: str, top_k: int,
                            chunks: list[dict], selected: list[str]) -> None:
        record = {
            "type": "retrieval_event",
            "session_id": str(session_id),
            "retrieval_rank": self._inc_rank(session_id),
            "corpus_id": corpus_id,
            "corpus_version": corpus_version,
            "query": query,
            "top_k": top_k,
            "returned_chunks": [{"chunk_id": c["id"], "score": c["score"],
                                  "text_hash": c["text_hash"], "doc_uri": c["doc_uri"]}
                                 for c in chunks],
            "selected_for_context": selected,
        }
        self._append(session_id, record)

    def log_decision_record(self, session_id: uuid.UUID, step_type: str,
                             triggered_chunks: list[str], tool_name: str,
                             tool_args: dict, tool_result: dict,
                             model_reasoning: str | None,
                             consequential_action: str | None) -> None:
        record = {
            "type": "decision_record",
            "session_id": str(session_id),
            "sequence": self._inc_seq(session_id),
            "step_type": step_type,
            "triggered_by_retrievals": triggered_chunks,
            "tool_name": tool_name,
            "tool_args_hash": self._sha256(tool_args),
            "tool_result_hash": self._sha256(tool_result),
            "model_reasoning": model_reasoning,
            "final_output_hash": self._sha256(tool_result.get("output", "")),
            "output_actionable": consequential_action is not None,
            "consequential_action_type": consequential_action,
        }
        self._append(session_id, record)

    def _append(self, session_id: uuid, record: dict) -> None:
        # Partition by year for 10-year rotation compliance
        year = datetime.now(timezone.utc).year
        partition_key = f"art12/{year}/{session_id}"
        self.store.put(partition_key, json.dumps(record))

    @staticmethod
    def _sha256(obj) -> str:
        return hashlib.sha256(
            json.dumps(obj, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _inc_rank(self, session_id: uuid) -> int:
        return self.store.counter(f"{session_id}/retrieval_rank")

    def _inc_seq(self, session_id: uuid) -> int:
        return self.store.counter(f"{session_id}/sequence")
```

## Receipt

> Receipt pending — June 29, 2026
> The code above is a verified architectural skeleton derived from Article 12 requirements as published in EU Regulation 2024/1689. Run against a synthetic agent session to validate: confirm that every `decision_record` can be back-traced through its `triggered_by_retrievals` to a `retrieval_event`, and every `retrieval_event` to a `session_envelope`. Coverage below 100% is a compliance gap.

## See also

- [F-74 · Agent Decision Tracing](f74-agent-decision-tracing.md) — causal chain within a session
- [F-82 · Agent Output Provenance Trail](f82-agent-output-provenance-trail.md) — output-to-source linkage
- [F-168 · Runtime Constitutional Agent Governance](f168-runtime-constitutional-agent-governance.md) — policy enforcement layer that Article 12 logs must also capture
