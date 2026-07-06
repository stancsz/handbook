# S-388 · Constrained Decoding for Hallucination Prevention

Agents generate fluent, confident text that exceeds what the context actually supports. The model doesn't "know" it doesn't know — it keeps producing plausible continuations. Constrained decoding forces the output to stay within a verifiable vocabulary or grammar, physically preventing the model from tokenizing claims that aren't anchored in the retrieved context.

## Forces

- LLMs are trained to be maximally fluent — fluency and fidelity are in tension, and the model optimises for fluency
- RAG retrieval is never 100% recall — the gap between retrieved context and generated output is where hallucination enters
- Post-generation fact-checking catches errors but adds latency and doesn't prevent the wasted generation
- Constrained decoding at the token level is the only way to prevent, not just detect, fabrication — but naive masking kills fluency entirely

## The move

**Use vocabulary-constrained or grammar-guided decoding to bound the output space to tokens consistent with retrieved context.**

Three practical tiers:

### Tier 1 — Vocabulary Masking (simplest)

Build a whitelist of valid tokens from retrieved documents + system knowledge. At each decoding step, zero out probabilities for tokens outside the whitelist.

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from collections import Counter
import re

class ConstrainedDecoder:
    """Token-level vocabulary mask from retrieved context."""

    def __init__(self, model_name: str = "mistralai/Mistral-7B-Instruct"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.float16, device_map="auto"
        )

    def build_mask(self, retrieved_contexts: list[str], max_tokens: int = 50000) -> set[int]:
        """Extract all tokens present in retrieved context."""
        valid_tokens: set[int] = set()
        for ctx in retrieved_contexts:
            # Whitelist context tokens (with some safety margin)
            tokens = self.tokenizer.encode(ctx, add_special_tokens=False)
            valid_tokens.update(tokens[:max_tokens])
        # Always allow punctuation, numbers, whitespace, newlines
        always_allowed = set(range(5, 256))  # ASCII punctuation + common
        always_allowed.update({self.tokenizer.pad_token_id})
        always_allowed.update({self.tokenizer.eos_token_id})
        valid_tokens.update(always_allowed)
        return valid_tokens

    @torch.no_grad()
    def generate(self, prompt: str, retrieved_contexts: list[str],
                 max_new_tokens: int = 256) -> str:
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        valid_token_ids = self.build_mask(retrieved_contexts)

        output_ids = inputs["input_ids"]
        past_key_values = None

        for _ in range(max_new_tokens):
            outputs = self.model(
                input_ids=output_ids,
                past_key_values=past_key_values,
                use_cache=True,
            )
            logits = outputs.logits[:, -1, :]  # [batch, vocab]
            past_key_values = outputs.past_key_values

            # Zero out invalid tokens
            mask = torch.ones_like(logits) * float("-inf")
            for tid in valid_token_ids:
                if tid < mask.shape[-1]:
                    mask[0, tid] = 0.0
            masked_logits = logits + mask

            # Temperature sampling
            probs = torch.softmax(masked_logits / 0.8, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)

            if next_token.item() == self.tokenizer.eos_token_id:
                break
            output_ids = torch.cat([output_ids, next_token], dim=-1)

        return self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
```

### Tier 2 — Grammar-Constrained (Outlines / lm-format-enforcer)

For structured outputs, use a formal grammar (JSON Schema, regex) to guide decoding:

```python
from outlines import generate, models, samplers
from outlines.integrations.transformers import TransformerTokenizer
import json

model_name = "mistralai/Mistral-7B-Instruct"
model = models.transformers(model_name, device="cuda")
tokenizer = TransformerTokenizer(model_name)

# Only allow tokens consistent with a valid JSON response
schema = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {"type": "string"}
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["answer", "sources", "confidence"]
}

# Guided generation — model can ONLY produce valid JSON
generator = generate.json(model, schema, sampler=samplers.multinomial(temp=0.3))
prompt = f"Context: {retrieved_context}\nAnswer the question as JSON:"
result_str = generator(prompt, max_tokens=512)
result = json.loads(result_str)
```

### Tier 3 — Context-Attribution Cross-Reference (strongest)

After vocabulary masking, verify each generated claim against the context before accepting it:

```python
def generate_with_attribution_check(
    decoder: ConstrainedDecoder,
    prompt: str,
    retrieved_contexts: list[str],
    claim_extractor,  # callable that extracts [subject, predicate, object] triples
    max_retries: int = 3,
) -> tuple[str, list[str]]:
    """
    Generate with masked vocabulary, then verify each claim.
    Unverifiable claims are masked in the retry round.
    """
    for attempt in range(max_retries):
        # Track masked terms per attempt
        masked_terms = set()
        for _ in range(attempt):
            masked_terms.update(decoder.add_masked_terms(attempt))

        output = decoder.generate(prompt, retrieved_contexts)

        # Extract and verify claims
        claims = claim_extractor(output)
        verified_sources = []
        unverifiable = []

        for claim in claims:
            # BM25 or semantic search against retrieved context
            if verify_claim(claim, retrieved_contexts):
                verified_sources.append(claim.text)
            else:
                unverifiable.append(claim.text)

        if not unverifiable:
            return output, verified_sources

        # Retry: mask tokens from unverifiable claims
        decoder.add_masked_terms(unverifiable)

    return output, verified_sources
```

**Key insight**: don't constrain what the model *thinks*, constrain what it *says*. The model still reasons freely — the mask only gates the output tokens.

## Receipt

> Receipt pending — 2026-07-02. The Outlines library integration is documented at https://github.com/outlines-dev/outlines; vocabulary masking requires custom logits processor implementation against the HuggingFace `generate()` API. The FSM approach (Tier 3 attribution cross-reference) is the most robust but has not been benchmarked in the handbook test harness.

## See also

- [S-04 · Structured Output](stacks/s04-structured-output.md) — the output-format companion; constrained decoding is the enforcement mechanism
- [S-385 · Agent Trajectory Evaluation: Process vs. Outcome Scoring](stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — evaluation layer downstream of constrained generation
- [S-78 · Agent-to-Human Escalation](stacks/s78-agent-to-human-escalation.md) — what to do when the constraint mask dead-ends (no valid next token)
