# R-11 · Agent Simulation Environments

Training an agent on a demo works until production. Training it on a few real tasks works until the distribution shifts. The gap is the same one that killed software QA in the 90s: you can't ship what you haven't tested against. For agents, that means synthetic environments — simulated infrastructure, APIs, user behaviors, and failure modes — where you can run millions of agent-hours without touching production systems or burning real-world resources. This is the discipline of agent simulation environments: building the world your agent lives in before you put it in the real one.

## Forces

- Real-world agent training is prohibitively expensive and slow: a customer-support agent that needs to learn from 50,000 interactions would require months and real users. Simulation lets you generate those interactions at scale
- Agent diversity requires environment diversity: an agent trained only on `grep` fails on `ripgrep`; one trained only on friendly APIs fails on adversarial ones. Real infrastructure doesn't vary on demand
- The bootstrapping problem is real: you need good agents to generate good training data, but you need good training data to build good agents — simulation breaks the cycle by generating data independent of the agent's current capability
- Environment fidelity is a spectrum: a mock HTTP server is cheap and low-fidelity; a mirror of your production system with synthetic users is expensive and high-fidelity. The engineering challenge is picking the right fidelity level for the capability you're trying to train
- Evaluation without simulation is post-hoc: you discover your agent fails on task X only after a user hits it. Simulation lets you pre-emptively enumerate failure modes

## The move

### Pattern 1 — Digital Twin Sandbox

Mirror your production environment with synthetic data. The agent operates against services that look, smell, and behave like the real thing — same API contracts, same error codes, same latency profiles — but all data is fabricated and no actions have real consequences.

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class SimulatedAPI:
    name: str
    base_url: str
    mock_handler: Callable
    latency_ms: tuple[int, int] = (50, 200)
    error_rate: float = 0.02  # 2% random errors to train resilience

def make_digital_twin(env_spec: dict) -> dict[str, SimulatedAPI]:
    """Build a suite of simulated services from an OpenAPI spec."""
    twins = {}
    for service_name, spec in env_spec.items():
        twins[service_name] = SimulatedAPI(
            name=service_name,
            base_url=f"http://localhost:9{len(twins)+1}00/{service_name}",
            mock_handler=build_mock_from_spec(spec),
            latency_ms=(spec.get("latency_min", 30), spec.get("latency_max", 300)),
            error_rate=spec.get("error_rate", 0.01),
        )
    return twins

# Usage: swap production endpoints for twin endpoints in agent config
twins = make_digital_twin(openapi_spec)
agent_config["tool_endpoints"] = {t.name: t.base_url for t in twins.values()}
```

**Key discipline**: the twin must fail the same way production fails. If your real API returns `429 Too Many Requests` under load, the twin must too. If it returns malformed JSON 0.1% of the time, the twin must match that rate.

### Pattern 2 — Agent World Model

Use a capable LLM to generate novel environments procedurally. Unlike digital twins (which mirror existing systems), world models generate new scenarios the agent hasn't seen — testing generalization beyond the training distribution. The Agent World Model (AWM) paper (2026) synthesizes 1,000+ diverse code-driven environments with databases for training tool-use agents at scale.

```python
def generate_world_model_scenario(domain: str, difficulty: str) -> dict:
    """Procedurally generate a novel environment configuration."""
    prompt = f"""Generate a realistic {difficulty} {domain} environment config.
Include: service APIs, database schema, user behaviors, failure modes.
Return a JSON environment spec the agent will operate in.

Domain: {domain}
Difficulty: {difficulty}"""
    
    spec = llm.structured_output(prompt, schema=EnvironmentSpec)
    return {
        "services": spec.apis,
        "data": generate_synthetic_db_dump(spec.schema, rows=spec.row_count),
        "failure_scenarios": spec.inject_failures,
        "ground_truth_answers": spec.expected_outcomes,
    }

# Train agent on 500 generated scenarios, evaluate on held-out 100
train_scenarios = [generate_world_model_scenario(d, lvl) for d in DOMAINS for lvl in ["easy","medium"]]
eval_scenarios = [generate_world_model_scenario(d, "hard") for d in DOMAINS]
```

**Key discipline**: validate that generated scenarios are actually solvable. World models can produce environments with no valid solution — quality filter the generated specs before using them as training data.

### Pattern 3 — Multi-Agent Scenario Simulation

Simulate the *users* and *collaborators* the agent interacts with using LLMs. A coding agent doesn't operate in isolation — it works with PMs, reviewers, and end-users. Replace humans with simulated agents to run thousands of collaborative scenarios cheaply.

```python
@dataclass
class SimulatedUser:
    role: str
    personality: str  # "impatient", "verbose", "ambiguous"
    llm: str

def run_scenario(agent, scenario, num_turns=10) -> Trajectory:
    user_agent = SimulatedUser(
        role=scenario.user_role,
        personality=scenario.user_personality,
        llm="claude-sonnet-4"
    )
    trajectory = Trajectory(scenario.initial_context)
    
    for turn in range(num_turns):
        # Agent acts
        agent_output = agent.step(trajectory.history)
        trajectory.add(agent_output)
        
        # User responds (simulated)
        user_prompt = f"Role: {user_agent.role}. Personality: {user_agent.personality}.
        Previous exchange: {trajectory.history}
        What does this user say next?"
        user_response = llm.complete(user_prompt)
        trajectory.add(user_response)
        
        if scenario.is_complete(trajectory):
            break
    
    return trajectory

# Run 10,000 simulated conversations to surface failure modes
results = [run_scenario(coding_agent, s) for s in SCENARIOS]
failure_clusters = cluster_by_failure_mode([r for r in results if not r.success])
```

### Pattern 4 — Tool Simulation for Scale

Build mock tool interfaces that behave like real APIs but are faster and cheaper. Particularly valuable for training tool-use agents where real API calls are expensive or rate-limited.

```python
class MockToolRegistry:
    """Register tools with optional real-backend and fallback simulation."""
    
    def __init__(self):
        self.tools: dict[str, ToolDef] = {}
    
    def register(self, name: str, spec: ToolDef, real_fn=None, sim_fn=None):
        self.tools[name] = ToolDef(
            name=name, spec=spec,
            real_fn=real_fn, sim_fn=sim_fn or self._default_simulator(spec)
        )
    
    def call(self, name: str, args: dict, mode: str = "sim") -> dict:
        tool = self.tools[name]
        fn = tool.real_fn if mode == "real" and tool.real_fn else tool.sim_fn
        return fn(args)
    
    def _default_simulator(self, spec: ToolDef):
        """Generate realistic mock responses from spec and schema."""
        def simulate(args):
            # Use LLM to generate a plausible response given the tool spec
            return llm.structured_output(
                f"Simulate calling {spec.name} with args {args}. Return realistic output.",
                schema=spec.output_schema
            )
        return simulate

# Train on 1M simulated tool calls, validate on 10K real ones
registry = MockToolRegistry()
registry.register("search_code", SEARCH_TOOL_SPEC, real_fn=real_search, sim_fn=sim_search)
```

### Pattern 5 — Failure Injection Simulation

Not just "does the agent work?" but "does the agent handle failure gracefully?" Inject failures systematically:

```python
FAILURE_MODES = [
    ("api_timeout", lambda: time.sleep(30)),
    ("rate_limit_429", lambda: HTTPError(429)),
    ("malformed_json", lambda: b'{"incomplete":'),
    ("auth_expired", lambda: HTTPError(401)),
    ("data_drift", lambda: return_stale_data()),
    ("partial_result", lambda: return_incomplete_results()),
]

def inject_failure(scenario: Scenario, mode: str):
    """Wrap a scenario with an injected failure at a random step."""
    inject_at = random.randint(1, scenario.num_steps - 1)
    failure_fn = dict(FAILURE_MODES)[mode]
    
    wrapped = copy(scenario)
    original_tool = wrapped.tools[scenario.target_tool]
    def failing_tool(*args, **kwargs):
        if wrapped.current_step == inject_at:
            return failure_fn()
        return original_tool(*args, **kwargs)
    wrapped.tools[scenario.target_tool] = failing_tool
    return wrapped
```

## Receipt

> Receipt pending — 2026-06-30. Real validation requires a running simulation pipeline with at least one digital twin and a trajectory corpus. The patterns above are grounded in published research (AWM arxiv:2602.10090, SWE-bench, WebArena) and production patterns observed across agentic deployments in 2026, but the full example pipeline has not been executed end-to-end in this session.

## See also

- [R-05 · Self-Evolving Agents](r05-self-evolving-agents.md) — simulation is the training ground for self-evolution; environment diversity drives the evolutionary pressure
- [S-194 · Synthetic Data for Fine-Tuning](stacks/s194-synthetic-data-fine-tuning-pipeline.md) — the data side of the same problem: generating high-quality training data without real-world collection
- [S-220 · Agentic Behavioral Regression Suite](stacks/s220-agentic-behavioral-regression-suite.md) — evaluation environments as a production discipline, not just a training tool
- [S-223 · Agent Sandboxing](stacks/s223-agent-sandboxing-code-execution.md) — isolation requirements when running agents in simulated vs. real environments
