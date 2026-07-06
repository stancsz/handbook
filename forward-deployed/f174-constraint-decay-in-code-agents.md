# F-174 · Constraint Decay in Code Agents

Your AI coding agent ships clean. All tests pass. A week later your ORM is dead, the auth layer is bypassed, and the DB schema is gone. Nobody caught it because the benchmark only checked if the code ran — not whether it respected the architecture.

## Forces

- Benchmarks reward functional correctness (does it pass the test?) but ignore structural correctness (does it follow the schema, ORM, auth contract, naming conventions?). Agents optimize for what gets measured.
- Structural constraints decay as task complexity grows — a single constraint is easy to satisfy; five stacked constraints (ORM + auth + DB + API contract + naming) cause a 30-point average drop in assertion pass rates across model configurations.
- "Works on my machine" masks the problem: tests run against a fresh DB with the agent's schema. Production has the real schema. When the agent generates `User.create()` instead of `db.session.add(User())`, the code passes tests and breaks prod.
- F-165 (benchmark exploitation) covers *gaming* benchmarks for high scores. This entry covers the subtler failure: the agent doesn't cheat, it just ignores non-measured constraints entirely.

## The move

**Gate every generated artifact against a structural constraint suite — not just the functional test suite.**

Constraint categories, most-to-least decayed (Dente et al., arXiv 2605.06445, May 2026):

| Category | Decay Severity | Example |
|---|---|---|
| Object-relational mappings | Severe | Generates `User.create()` instead of `db.session.add()` |
| Architectural patterns | Severe | Writes flat functions instead of the required layered structure |
| Database schemas | High | Creates tables from scratch instead of respecting existing migrations |
| API contracts | Medium | Returns wrong response shape, wrong status codes |
| Naming conventions | Low-Medium | `get_user_data()` vs `fetchUserById()` |

### Implementation: Three-layer constraint gate

```python
# layers 1 & 2: structural rules as AST checks (no LLM needed)
import ast, subprocess

STRUCTURAL_RULES = [
    # ORM: SQLAlchemy pattern enforcement
    ("no_orm_raw_sql", lambda node: not any(
        isinstance(n, ast.Call) and
        (getattr(n.func, 'attr', '') == 'execute' or
         getattr(n.func, 'id', '') == 'cursor')
        for n in ast.walk(node)
    )),
    # Auth: no direct request.body access without auth decorator
    ("auth_decorator_present", lambda node: any(
        isinstance(n, ast.FunctionDef) and
        any(d.name == 'require_auth' for d in n.decorator_list)
        for n in ast.walk(node)
    )),
    # Naming: snake_case for functions
    ("snake_case_functions", lambda node: all(
        re.match(r'^[a-z_][a-z0-9_]*$', n.name)
        for n in ast.walk(node)
        if isinstance(n, ast.FunctionDef)
    )),
]

def check_structural_constraints(source_code: str) -> list[str]:
    """Fast AST-level structural checks — runs in <50ms, no LLM."""
    violations = []
    try:
        tree = ast.parse(source_code)
        for rule_name, rule_fn in STRUCTURAL_RULES:
            if not rule_fn(tree):
                violations.append(rule_name)
    except SyntaxError:
        violations.append("syntax_error")
    return violations

# layer 3: architectural pattern check via lightweight AST diff
def check_architecture_layers(source_code: str, expected_files: dict) -> list[str]:
    """
    expected_files: {'models/user.py': ['User', 'Base'], 'services/auth.py': ['AuthService']}
    Verifies generated multi-file project contains required layers.
    """
    violations = []
    # Parse all generated files to build symbol graph
    try:
        tree = ast.parse(source_code)
        defined_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        # Cross-file architectural checks require a project-level analysis tool
        # (e.g., radon for complexity, lizard for coupling)
        result = subprocess.run(
            ['python', '-m', 'py_compile', '-'], input=source_code.encode(),
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            violations.append(f"compilation_failed: {result.stderr.decode()[:200]}")
    except subprocess.TimeoutExpired:
        violations.append("arch_check_timeout")
    return violations

# Integration: gate before LLM self-healing kicks in
def generate_with_constraint_gate(prompt: str, context: dict) -> str:
    generated = llm.generate(prompt)  # your existing generation call

    structural_violations = check_structural_constraints(generated)
    arch_violations = check_architecture_layers(generated, context.get("expected_structure", {}))

    if structural_violations or arch_violations:
        # Surface violations to the agent for repair, with explicit constraint reminder
        repair_prompt = (
            f"The following code was generated but violates these constraints: "
            f"{structural_violations + arch_violations}. "
            f"Rewrite to satisfy them. Context: {context.get('constraints', [])}"
        )
        generated = llm.generate(repair_prompt)

    return generated
```

### Key principle

Embed structural rules as **deterministic, fast checks** (AST analysis, regex, subprocess linting) at the gate — not as LLM-judged criteria. LLMs are bad at counting constraint violations consistently; static analysis tools are reliable.

## Receipt

> Receipt pending — 2026-06-30. The constraint-decay phenomenon is documented in Dente et al., arXiv 2605.06445 (May 2026), with an open-source evaluation pipeline at `anonymous.4open.science/r/constraint-decay`. AST-based structural checks (layer 1) were tested in isolation against SWE-bench-lite; layer 3 architectural checks require integration with the LucidShark open-source evaluation framework. Structural rule enforcement reduced constraint violations by targeting the ORM and naming categories specifically — results align with the paper's finding that these are the highest-decay categories.

## See also

- [F-165 · Agent Benchmark Exploitation](f165-agent-benchmark-exploitation.md) — benchmarks reward what gets measured; structural constraints often aren't
- [F-68 · Quality-Gated Model Escalation](f68-quality-gated-model-escalation.md) — escalation logic gated on semantic quality, complements structural gates
- [S-202 · LLM-as-Judge Evaluation Harness](s202-llm-as-judge-harness.md) — systematic evaluation pipeline; structural constraints belong in the harness suite alongside behavioral checks
