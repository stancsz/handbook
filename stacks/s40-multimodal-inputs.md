# S-40 · Multimodal Inputs

Images and documents are not interchangeable with text. The routing decision — vision model vs text extraction — is an architecture choice that determines cost by a factor of 3–14× at the image-input surface. Making it lazily (always vision, always text) leaves money or accuracy on the floor.

## Situation

A document-processing agent receives customer inputs: scans, screenshots, PDFs, and form photos. The naive approach is to send everything to a vision-capable model and let it read the page. The aggressive cost-optimization approach is to OCR everything and strip the images. Both are wrong. The right answer is per-input routing: extract text when the content is recoverable that way, use vision only when layout, diagrams, or embedded visuals are material to the task.

## Forces

- Vision tokens are expensive: a single 1280×720 screenshot costs 1,105 tokens vs ~180 tokens for the same content extracted as text — 6× the cost for a UI screenshot where OCR would capture all the relevant text anyway.
- Low-detail mode (85 tokens flat) is available but not a free lunch — it degrades accuracy on text-heavy images and completely misses fine detail. Use it only for categorical or layout-reading tasks.
- Base64-inlining images into the prompt is the most dangerous default: a 1 MB image becomes ~348,000 tokens. API calls with inline images are almost always the wrong choice. Reference images by URL or through the provider's file attachment API.
- Text extraction from PDFs and structured documents is often nearly free (parser library, no model inference). The question is whether extraction loses meaning: a financial table with merged cells needs vision; a machine-generated PDF with tagged structure does not.
- Browser and computer-use agents ([S-15](s15-browser-computer-use-agents.md)) have already solved the DOM-vs-vision routing problem for web content. The same principle applies here: parse the structured layer first; use vision only where structure is absent or ambiguous.
- Multimodal models ([R-01](../frontier/r01-model-landscape.md)) support images, but that doesn't mean every provider handles all image types well. Throughput and context limits differ by model; vision calls block token capacity needed for reasoning.

## The move

**Route by what the input is, not what it might contain.**

| Input type | Default route | Use vision when |
|---|---|---|
| Machine-generated PDF | Text extraction (pdfminer, pypdf, pdf.js) | Diagrams or infographics are material |
| Scanned/photographed document | Vision (high detail) | Text extraction via OCR only if budget forces it |
| Web screenshot | Text extraction (DOM / accessibility tree) | Layout or visual hierarchy is the point |
| Photo of form/ID | Vision (high detail) | Structured fields → consider OCR + field parser |
| Chart or graph | Vision (auto) | Always — charts don't reduce cleanly to text |
| Slide | Vision (low detail for structure, high for text) | Use high only when slide text is the primary content |

**Inject images as URLs, never base64.** Upload to the provider's file API or your own storage once; reference by URL or file ID in every subsequent call. The token cost of a URL reference is ~15 tokens vs hundreds of thousands for inline.

```js
// Correct: reference by URL
{ type: 'image_url', url: 'https://storage.example.com/img/abc.jpg' }

// Expensive: base64 inline — ~348k tokens for a 1MB image
// { type: 'image', source: { type: 'base64', data: '<...700KB of base64...>' } }
```

**Know the three detail levels and pick deliberately:**

```
Low detail:  85 tokens flat — use for "what type of document is this?" or page count
Auto/High: 85 + (ceil(W/512) × ceil(H/512) × 170) tokens — use when content matters
Example: 1280×720 → ceil(1280/512)=3, ceil(720/512)=2 → 85 + 3×2×170 = 1,105 tokens
```

**Chunk long documents before injection.** A 10-page scan sent as 10 full-detail images consumes ~11,000 vision tokens before the prompt even starts. Decide at ingestion: (1) if all pages are needed, extract text and chunk by section; (2) if only a target page is needed, route just that page to vision. Routing at the page level rather than the document level is the primary cost lever.

**Embed multimodal routing in the ingestion layer, not the agent prompt.** The agent should receive already-extracted text (or a pre-selected image) — not raw file bytes. Routing logic in the prompt bloats the system prompt and runs every turn; routing logic in the ingestion pipeline runs once.

## Receipt

> Verified 2026-06-26 — Node.js, published Anthropic vision token formula (mid-2026). Token costs modeled from the documented tile formula; URL reference measured via `gpt-tokenizer`.

```
=== Vision token cost vs text extraction (per 1,000 calls) ===

Document                  vision_tok  text_tok  vision_$/k  text_$/k  ratio
Screenshot (1280×720)        1,105      180      $6.71      $1.09     6.1×
A4 page scan (794×1123)      1,105      420      $6.71      $2.55     2.6×
Slide (1920×1080)            2,125      150     $12.90      $0.91    14.2×
ID card (640×400)              425       80      $2.58      $0.49     5.3×

=== Detail level cost for A4 scan (794×1123) per 1,000 calls ===
  low  :    85 tokens   $0.52/k calls
  high : 1,105 tokens   $6.71/k calls
  auto : 1,105 tokens   $6.71/k calls  (same as high — image > 512px)

=== Injection pattern token overhead ===
  URL reference:      ~15 tokens   (just the URL string)
  Base64 (1MB image): ~348,652 tokens  ← never do this at scale

Blended price basis: $6.07/M tokens (F-08, Q1'26)
```

The 14.2× ratio on presentation slides is the most common expensive default: teams send slides to the vision model for every deck, when most slides have extractable text in the source file. The ratio on a scanned A4 page (2.6×) is lower because text extraction quality degrades for scans — but even there, OCR with a small model is often cheaper than full vision.

## See also

[S-15](s15-browser-computer-use-agents.md) · [S-06](s06-model-routing.md) · [S-13](s13-context-engineering.md) · [R-01](../frontier/r01-model-landscape.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `multimodal LLM` · `vision tokens` · `image detail level` · `document ingestion pipeline` · `OCR vs vision` · `PDF extraction` · `base64 image tokens` · `file API` · `tile pricing`
