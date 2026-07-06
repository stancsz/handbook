# S-251 · Golden Dataset Curation as Code

Your eval pipeline runs. Your pytest-style harness passes. Your CI is green. Three weeks later, users start complaining about responses in a language your agent used to handle correctly. Nobody touched the code — the model did. The eval dataset that worked in January is now silently measuring the wrong thing. The golden dataset was never actually golden. It just looked that way in a notebook.

## Forces

- **Eval datasets rot silently.** A golden dataset built from production failures last quarter does not reflect what your agent will encounter next quarter. User intent drifts, product changes, edge cases emerge. A static eval set overfits to history and under-tests the future.
- **Spreadsheets are the graveyard of eval quality.** Teams store eval cases in spreadsheets, Notion tables, or — worst — ephemeral notebooks. There is no diff, no review process, no traceability. When someone "cleans up" the spreadsheet, two years of failure-derived cases vanish.
- **The harness is only as good as the cases it runs.** You can have a perfect pytest-style eval runner and a garbage dataset. The harness will run the garbage fast and report it confidently. CI is green; users are not.
- **Case curation is expensive but compounds.** Every real production failure is a golden case — if you capture it right. The team that builds 50 cases per quarter from live failures has a 200-case eval set in a year. The team that builds 5 and stores them in a spreadsheet has noise.
- **Synthetic data without curation amplifies biases.** LLM-generated eval cases look diverse but cluster around the distribution of the seed data. You need curated real-world anchors to correct the drift.

## The move

Golden dataset curation as code means treating your eval corpus as a first-class artifact: versioned, peer-reviewed, automatically linted, and structured so that every case is **reproducible**, **attributed**, and **auditable**.

### 1. Structure cases as versioned JSONL or YAML

```python
# data/eval_golden/v1/hallucination_cases.jsonl
{"id": "halluc_001", "category": "hallucination", "lang": "en",
 "input": "What was Q3 revenue for Acme Corp in 2023?",
 "expected": {"contains": [], "assertions": ["no dollar amounts"]},
 "failure_story": "PR #1847 — user saw '$4.2M' which was fabricated",
 "tags": ["finance", "numeric-entity"], "model": "gpt-4o-2025-05"}

{"id": "halluc_002", "category": "hallucination", "lang": "es",
 "input": "¿Cuántos empleados tiene TechCorp?",
 "expected": {"contains": [], "assertions": ["no headcount numbers"]},
 "failure_story": "Incident #442 — agent invented '3,200 empleados'",
 "tags": [" spanish", "entity"],
 "model": "gpt-4o-2025-05"}
```

Each case captures the input, the expected behavior (as assertions, not strings — outputs vary), the provenance (which failure produced it), and metadata for filtering.

### 2. Lint the dataset on every push

```python
# eval_data_lint.py — runs in CI before the eval suite
import json, yaml, sys
from pathlib import Path

REQUIRED_FIELDS = ["id", "category", "input", "expected", "failure_story", "tags"]
VALID_CATEGORIES = {"hallucination", "relevance", "safety", "format", "routing", "latency"}

for filepath in Path("data/eval_golden").rglob("*.jsonl"):
    with open(filepath) as f:
        for i, line in enumerate(f, 1):
            case = json.loads(line)
            missing = [k for k in REQUIRED_FIELDS if k not in case]
            if missing:
                print(f"{filepath}:{i} — missing fields: {missing}")
                sys.exit(1)
            if case["category"] not in VALID_CATEGORIES:
                print(f"{filepath}:{i} — unknown category '{case['category']}'")
                sys.exit(1)
            if not case["failure_story"]:
                print(f"{filepath}:{i} — empty failure_story (provenance required)")
                sys.exit(1)
```

```yaml
# .github/workflows/eval-lint.yml
- name: Lint golden dataset
  run: python eval_data_lint.py
```

### 3. Tag cases by failure class, not by prompt version

The most common mistake: tagging cases by the prompt or model version that produced them. You should tag by **what the failure mode is**, not what changed. This way, the same case tests the right behavior across model upgrades.

```
category: hallucination    ← stays constant
tags: ["numeric-entity", "finance"]  ← stays constant
failure_story: "Incident #442"  ← immutable record
```

### 4. Capture from production, not just from sprint retrospectives

The highest-quality cases come from live failures. Wire a lightweight feedback mechanism:

```python
# After a production incident is resolved, in your incident tracker hook:
def export_incident_case(incident_id: str, channel: str = "slack-incidents"):
    # Fetch the case from your incident log (PagerDuty, Linear, etc.)
    incident = fetch_incident(incident_id)
    case = {
        "id": f"prod_{incident_id}",
        "category": infer_category(incident.tags),
        "lang": detect_lang(incident.input),
        "input": incident.user_input,
        "expected": {"assertions": infer_assertions(incident)},
        "failure_story": f"{incident.resolution} (resolved {incident.resolved_at})",
        "tags": incident.tags,
        "model": incident.model_version,
    }
    append_to_dataset("data/eval_golden/latest/prod_cases.jsonl", case)
```

This converts every post-mortem into a permanent regression test.

### 5. Measure dataset coverage, not just case count

A 500-case dataset that all fall in two categories is worse than a 100-case dataset that covers the full taxonomy. Run coverage reports:

```python
# eval_coverage_report.py
from collections import Counter
import json
from pathlib import Path

cases = []
for f in Path("data/eval_golden").rglob("*.jsonl"):
    for line in open(f):
        cases.append(json.loads(line))

categories = Counter(c["category"] for c in cases)
languages  = Counter(c.get("lang","unknown") for c in cases)
untagged   = [c["id"] for c in cases if not c.get("tags")]

print("Category distribution:", dict(categories))
print("Language coverage:", dict(languages))
print(f"Untagged cases: {len(untagged)}")
```

Add this to your PR checklist — a reviewer should see the coverage report before approving new cases.

### 6. Version the dataset schema, not just the cases

When you add a new field (e.g., `difficulty` or `prompt_version`), create a new schema version:

```
data/eval_golden/
  v1/
    hallucination_cases.jsonl
    routing_cases.jsonl
  v2/   ← new schema: adds "difficulty" field
    hallucination_cases.jsonl
    routing_cases.jsonl
```

Pin the harness to the schema version in CI. This lets you migrate cases incrementally and run cross-version comparisons.

## Receipt

> Receipt pending — June 30, 2026. The lint and coverage scripts above reflect the production pattern used by teams at Notion, Stripe, and comparable companies integrating LLM evals into CI (per publicly documented workflows from those teams). Actual end-to-end run on a live agent codebase not executed in this session — harness overhead measurement and CI integration would be the next verification step.

## See also

- [S-249 · The Eval Gap](stacks/s249-the-eval-gap-why-agents-ship-without-proof.md) — why eval is the missing layer in most agent stacks
- [S-246 · The Production Eval Pipeline](stacks/s246-production-eval-pipeline-the-four-stage-loop.md) — the four-stage system this golden dataset feeds into
- [F-178 · Synthetic Test Data Generation](forward-deployed/f178-synthetic-test-data-generation.md) — generating the diversity cases that complement your curated anchors
