# F-167 · RAG Faithfulness Gate

When your agent retrieves K chunks and generates an answer, the answer can still invent facts the chunks never contained. The retrieved context is used — but the model drifts beyond it. A faithfulness gate intercepts this before the answer ships.

## Forces
- Retrieval recall and retrieval precision both look fine in eval, yet a customer flags a fabricated paragraph two days later
- The model has every framework feature it needs — RAG, citations, tool use — except the one that would catch hallucination in generated text
- Standard QA benchmarks (BLEU, ROUGE) measure overlap with a reference answer, not whether that answer was grounded at all
- LLM-as-a-judge without a grounding check will pass confidently wrong answers

## The move

**Faithfulness is a separate axis from relevance and recall.** Three metrics to distinguish:

| Metric | Question | Method |
|--------|----------|--------|
| **Context Precision** | Did we retrieve the right chunks for the right positions? | Binary relevance × rank-weighted score |
| **Answer Faithfulness** | Do all claims in the answer trace back to retrieved context? | NLI entailment between answer + each chunk |
| **Citation Accuracy** | Do the cited sources actually support the claims? | Chunk-level entailment on cited spans only |

**Implement the gate:**

```python
from transformers import pipeline
import re

class FaithfulnessGate:
    def __init__(self, model_name="ibm-granite/granite-guardian-3-3b"):
        # Lightweight NLI model — runs on CPU, ~50ms/chunk
        self.nli = pipeline(
            "text2text-generation",
            model=model_name,
            tokenizer=model_name,
            device=-1,
        )

    def score(self, question: str, answer: str, chunks: list[str]) -> dict:
        """
        Returns per-chunk faithfulness scores and an overall pass/fail.
        """
        sentences = self._split_sentences(answer)
        results = []

        for i, chunk in enumerate(chunks):
            chunk_claims = []
            for sent in sentences:
                # Prompt-based NLI: does the chunk entail this claim?
                entail = self._entail(chunk, sent)
                chunk_claims.append({"sentence": sent, "entailed": entail})

            # Proportion of chunk-sentences that are entailed
            chunk_score = sum(1 for c in chunk_claims if c["entailed"]) / max(len(sentences), 1)
            results.append({"chunk_index": i, "score": chunk_score, "claims": chunk_claims})

        overall = sum(r["score"] for r in results) / len(results) if results else 0
        return {
            "overall_faithfulness": overall,
            "chunk_scores": results,
            "passed": overall >= 0.85,  # threshold — tune to your domain
            "failed_sentences": [
                (r["chunk_index"], c["sentence"])
                for r in results
                for c in r["claims"]
                if not c["entailed"]
            ],
        }

    def _entail(self, premise: str, hypothesis: str) -> bool:
        prompt = (
            f"Given the following context, determine if the statement is supported.\n"
            f"Context: {premise}\n"
            f"Statement: {hypothesis}\n"
            f"Output only: YES or NO."
        )
        result = self.nli(prompt, max_new_tokens=3)[0]["generated_text"].strip().upper()
        return "YES" in result

    def _split_sentences(self, text: str) -> list[str]:
        # Basic sentence splitting — replace with spacy or stanza for production
        import re
        return [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]
```

**Where to wire it in:**
1. **Post-generation gate** — after the LLM generates but before streaming the answer, run the gate. If `passed=False`, inject a correction turn: "One or more claims could not be verified against the retrieved context. Revise."
2. **CI regression test** — for each eval case, store `(question, chunks, answer)` tuples and assert `score >= threshold`. Catch regressions on prompt or model changes.
3. **Production sampling** — run the gate on a 5% random sample of live queries. Alert if overall faithfulness drops below threshold.

**Calibration note:** NLI models have known biases — they under-penalize logical paraphrase and over-penalize surface-form mismatch. Calibrate with a golden set of 50 labeled (answer, chunk, entailed/not) examples specific to your domain. Even a small golden set dramatically improves threshold selection.

## Receipt
> Receipt pending — June 29, 2026

## See also
- [F-07 · Evaluation-Driven Development](f07-evaluation-driven-development.md) — wiring quality gates into CI
- [F-02 · Evaluation at Scale](f02-evaluation-at-scale.md) — LLM-as-a-judge layer tradeoffs
- [S-07 · RAG](stacks/s07-rag.md) — retrieval architecture context
- [F-32 · Agent Output Diffing](stacks/s94-agent-output-diffing.md) — tracking behavioral drift
