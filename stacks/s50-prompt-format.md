# S-50 · Prompt Format and Structure

How you format a prompt changes how reliably the model follows it. XML tags, Markdown headers, bold labels, and prose are not interchangeable — they differ in how the model parses sections, how consistently it applies constraints, and whether the output can be extracted programmatically. The cost difference is within 10%; the compliance difference is larger.

## Situation

A system prompt uses prose paragraphs — instructions flow naturally, constraints are embedded in sentences, output shape is described in the last sentence. It works most of the time. When it doesn't, there's no clear section to update: is the constraint in paragraph two or three? Does "respond concisely" outweigh "explain your reasoning" mentioned later? Converting to XML-tagged sections fixes the section boundary ambiguity and makes constraint position explicit.

## Forces

- Model compliance with constraints degrades as prose length grows. A constraint buried in paragraph five of a prose prompt carries less weight than the same constraint under a `<constraints>` tag at a defined position. Instruction-tuned models are trained to follow structured prompts; they infer section intent from prose, which introduces ambiguity.
- Token overhead for structure is minimal: XML tags add ~5% overhead vs prose for the same content; Markdown headers are −10% (more compact). The cost of structure is noise; the benefit is parsing reliability.
- Format is model-family specific. Claude was trained on XML-tagged prompts — `<instructions>`, `<context>`, `<examples>` are parsing anchors from pre-training. GPT-family models respond better to Markdown. Gemini tends to handle examples better than abstract instructions. Pick the format your deployed model was trained on.
- Output format follows the same logic. If you want parseable output, XML tags in the output are extractable with a regex; JSON is parseable with `JSON.parse`. Prose output requires ad-hoc extraction and breaks when phrasing varies.
- The format of examples matters. Each example section should use the same format as the expected output. If output is `{"priority": "high"}`, every example should return exactly that shape — not `priority: high` or `high (priority)`.
- Caching is format-neutral. A static system prompt is cacheable ([S-08](s08-prompt-caching.md)) regardless of whether it uses XML, Markdown, or prose. The cache key is the token sequence; the format does not affect cacheability.

## The move

**Match the prompt format to your deployed model family. Use XML for Claude, Markdown for GPT.**

**For Claude (XML tags):**
```xml
<identity>
You are a customer support agent for Acme Corp software.
</identity>

<scope>
Answer questions about billing, accounts, and plans only.
</scope>

<constraints>
Do not speculate about the product roadmap.
Do not offer discounts not listed on the pricing page.
</constraints>

<output>
Reply in 1-3 sentences. Return JSON: { "response": "...", "escalate": boolean }
</output>
```

**For GPT-family (Markdown):**
```markdown
## Identity
You are a customer support agent for Acme Corp software.

## Scope
Answer questions about billing, accounts, and plans only.

## Constraints
- Do not speculate about the product roadmap.
- Do not offer discounts not listed on the pricing page.

## Output
Reply in 1–3 sentences. Return JSON: { "response": "...", "escalate": boolean }
```

**Format by section type:**

| Section | Best format | Why |
|---|---|---|
| Identity / role | Single sentence, no tags needed | Parsed correctly in any format |
| Long constraint list | Bullet list inside a tag/header | Each bullet is a discrete rule; easier for model to enumerate |
| Examples | Consistent with expected output format | Model learns format from the examples |
| Output contract | Explicit inside `<output>` or `## Output` | Most important to have in a named section — it's what breaks downstream code |

**Tag naming: use nouns, not verbs.** `<context>` not `<this-is-the-context>`. `<examples>` not `<here-are-examples>`. Tags are section labels, not sentences.

**Custom tags for multi-turn injection.** When injecting retrieved content per-turn, use custom tags to mark boundaries: `<retrieved_context>...</retrieved_context>`. This tells the model (and you) exactly where injected content begins and ends, preventing instruction-data confusion ([F-13](../forward-deployed/f13-prompt-injection.md)).

**Output tags for extractable responses.** Ask the model to wrap its answer in a tag, then extract with regex:
```js
// Prompt: "Wrap your answer in <answer>...</answer>"
const answer = response.match(/<answer>([\s\S]*?)<\/answer>/)?.[1]?.trim();
```
This is more robust than JSON parsing for single-value extractions — a model that produces `<answer>high</answer>` is easier to parse than one that might produce `{"priority": "high"}` or `priority: high` or `The priority is: high`.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Same four-section system prompt (identity, scope, constraints, output) encoded in four formats; token counts measured directly. Output format comparison measured on a realistic response string.

```
=== System prompt format comparison (same content) ===

Format         tokens   vs prose
XML tags           88   +4 tokens  (+5%)
Markdown h1        76   −8 tokens  (−10%)
Bold labels        76   −8 tokens  (−10%)
Prose (none)       84   baseline

Format overhead is noise — within ±10%. Choose by model family, not token count.

=== Output format token cost (same response content) ===
XML output (<response>...</response><escalate>...</escalate>): 22 tokens  → regex-extractable
JSON output ({"response":"...","escalate":false}):            18 tokens  → JSON.parse
Prose output:                                                  20–60 tokens  → ad-hoc extraction

=== Compliance tradeoffs (documented, directional) ===
XML tags (Claude):     Strongest constraint compliance; output tags are regex-extractable
Markdown (GPT):        Strong for GPT-family; Claude handles correctly
Bold labels:           Moderate; no architectural compliance advantage
Prose:                 Weakest; model infers section boundaries; most constraint drift
```

The token overhead from structure is +5% for XML tags. The compliance gain is not measurable in a local test without A/B evals, but it is the documented advantage of structured prompts in Anthropic's own guidance — constraints under a `<constraints>` tag are treated as section-level rules, not inline suggestions.

## See also

[S-36](s36-system-prompt-architecture.md) · [S-16](s16-prompting.md) · [S-04](s04-structured-output.md) · [S-08](s08-prompt-caching.md) · [F-13](../forward-deployed/f13-prompt-injection.md) · [S-59](s59-instruction-density.md)

## Go deeper

Keywords: `prompt format` · `XML tags` · `Markdown prompt` · `structured prompt` · `output tags` · `prompt sections` · `constraint compliance` · `Claude XML` · `GPT Markdown`
