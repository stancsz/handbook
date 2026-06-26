# R-10 · Speculative Decoding

Autoregressive generation is slow not because the GPU can't compute fast enough, but because it can't load model weights fast enough. Each token step moves billions of parameters across memory before doing any arithmetic. Speculative decoding sidesteps this by using a cheap draft model to propose several tokens at once, then verifying them all in a single parallel pass of the large model.

## Forces

- Transformer decoding is memory-bandwidth-bound: one token = one full weight-load pass, no matter how small the compute is
- GPU arithmetic units sit idle during decoding — the bottleneck is data movement, not FLOPs
- Standard autoregressive generation cannot be parallelized: each token depends on all previous tokens
- Quantization and pruning trade quality for speed; speculative decoding is provably lossless — accepted tokens follow the exact same distribution as if the large model had generated them alone
- A separate draft model adds complexity; not all deployments can afford to run two models simultaneously

## The move

**Draft:** run a small, fast model to generate K candidate tokens (K = 4–8 typically).

**Verify:** run one forward pass of the large target model over all K draft tokens in parallel.

**Accept or reject:** compare the target model's per-token probabilities against the draft's. Accept tokens where the draft distribution matches well; at the first significant mismatch, resample that token from the target model and discard the rest of the draft.

This rejection-sampling scheme is the mathematical guarantee: accepted tokens are distributed exactly as if the target model had generated them one-at-a-time.

**Speedup math:** when acceptance rate R > 0.8 and the draft model is cheap (say 10× smaller), you get approximately K × R accepted tokens per verifier call instead of 1. Real speedups: 2–3× latency at zero quality loss.

**Variants:**
- **Medusa** — adds parallel prediction heads directly onto the LLM; no separate draft model; tree-based verification pass; comparable or higher speedup than the two-model variant
- **Self-speculative** — the large model itself skips intermediate transformer layers during drafting, then runs the full model for verification
- **EAGLE** — trains a lightweight auxiliary model on the target model's intermediate representations; high acceptance rates because the drafter has access to target-model internals

**Production availability:** speculative decoding is now built into vLLM, SGLang, and TensorRT-LLM. Enabling it is typically a one-line flag change; the quality guarantee means no re-evaluation is needed.

## Receipt

> Receipt pending — 2026-06-26. Speculative decoding requires a serving framework that exposes it (vLLM `--speculative-model`, SGLang's native support, or TGI). Ollama does not expose this control. Literature and production deployments at Google (AI Overviews), vLLM, and SGLang consistently report 2–3× latency reduction at mathematically identical output quality. The losslessness proof is in the original Chen et al. (2023) paper — rejection sampling from the target distribution is the mechanism, not approximation.

## See also

[R-08](r08-inference-time-compute-scaling.md) · [R-01](r01-model-landscape.md) · [R-04](r04-small-language-models.md) · [S-06](../stacks/s06-model-routing.md) · [S-02](../stacks/s02-context-budget.md)

## Go deeper

Keywords: `speculative decoding` · `draft-then-verify` · `Medusa decoding` · `EAGLE speculative` · `vLLM speculative model` · `acceptance rate` · `rejection sampling` · `Chen et al. 2023` · `memory bandwidth bottleneck`
