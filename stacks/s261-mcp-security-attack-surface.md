# S-261 · MCP Security — The Attack Surface You Inherited

Your agent connects to 12 MCP servers. Three are third-party. One of them runs on a server you don't own, processes your agent's queries, and returns tool results your agent trusts blindly. You have just inherited an attack surface you didn't design and probably haven't audited.

## Forces

- **MCP makes the tool-integration attack surface your problem.** Before MCP, each tool your agent called was code you wrote or controlled. With MCP, you connect to remote servers — shared, third-party, or internal — whose code your agent trusts implicitly. A malicious or compromised MCP server returns crafted responses that can manipulate your agent's reasoning, exfiltrate context, or trigger unintended tool calls.

- **Tool results are LLM input — and LLM input is attack surface.** MCP's `tool` result format feeds directly into your agent's context window. If an MCP server is adversarial or breached, it can inject prompt instructions, suppress safety filters, or redirect goals. This is prompt injection, but through a trusted tool channel instead of a user message.

- **The supply chain for MCP servers has no curation.** npm has 2M packages. PyPI has 500K. The MCP server ecosystem is new and unregulated — anyone can publish a server, and agents are consuming them without verifying code, permissions, or behavior. The equivalent of `pip install unknown-vendor` is now `mcp install finance-tools` in your agent config.

- **You trusted the tool call; you didn't audit the server.** Standard security assumes a tool call is a local function call. With MCP, the tool call crosses a network boundary to a server you don't control. The server sees the full request payload, can log it, modify responses, or return different data on repeated calls. Most teams using MCP have never audited a single server they depend on.

- **CVE-2026-2256 landed March 2026.** Prompt injection through an MCP server took over enterprise agents in production. No patch was available at disclosure. This is not theoretical — it is already a real-world incident class.

## The move

MCP security requires three practices that most teams have not adopted: **server provenance**, **output sanitization**, and **capability scoping**.

### 1. Pin server sources — don't pull at runtime

```yaml
# ❌ Risky: dynamic server from a repo you don't control
mcp_servers:
  - source: https://registry.agentic-tools.dev/search?q=finance

# ✅ Better: pinned, versioned servers with verified sources
mcp_servers:
  - name: filesystem
    source: github.com/modelcontextprotocol/servers?ref=v1.2.0
    hash: sha256:a3f8c...   # verified binary/tarball hash

  - name: slack
    source: github.com/my-company/mcp-slack#v2.1.3
    hash: sha256:b7d2c...
```

Store server URLs, versions, and SHA-256 hashes in your infrastructure config (Vault, AWS Secrets Manager, or similar). Audit additions like you audit `package.json` dependencies.

### 2. Treat MCP tool results as untrusted input

Every tool result from an external MCP server goes through your sanitization layer before entering the agent context:

```python
from mcp import Client
from agent_framework.sanitizer import sanitize_tool_result

client = Client()

async def call_mcp_tool(server_name: str, tool_name: str, params: dict) -> str:
    raw_result = await client.call(server_name, tool_name, params)

    # Sanitize before feeding to agent
    sanitized = sanitize_tool_result(
        raw_result,
        strip_markdown=True,       # remove formatting attacks
        truncate_length=8000,      # prevent context overflow injection
        remove_instructions=True,   # strip any text that looks like directives
        allow_lists_only=True,     # if result looks like structured data, parse it
    )
    return sanitized
```

`remove_instructions=True` uses a lightweight pattern matcher to detect attempts to inject agent directives (lines starting with "Ignore previous instructions", "SYSTEM:", "You are now", etc.). It is not a security boundary — it is a friction layer that blocks naive attacks.

### 3. Scope MCP server capabilities to minimum privilege

MCP servers should declare exactly what they can do, and your agent should only load servers with the capabilities it needs for the current task:

```python
from mcp import CapabilityScope

# ❌ Agent has filesystem + email + database + slack — all at once
agent = Agent(tools=["*"])  # wildcard = everything

# ✅ Least-privilege: task-scoped tool availability
def create_task_agent(task_type: str) -> Agent:
    scopes = {
        "code_review":   ["git", "filesystem:read", "github:read"],
        "customer_comms": ["email:send", "crm:read"],
        "data_analysis": ["database:read", "filesystem:write"],
    }
    allowed = scopes.get(task_type, [])
    return Agent(tools=allowed, policy=CapabilityScope.LOCKED)
```

Lock the scope at agent creation. If the agent tries to call a tool outside its scope, the MCP client raises a `CapabilityViolation` — do not silently fall back.

### 4. Audit MCP server traffic in staging

Before deploying a new MCP server to production, run it in shadow mode:

```bash
# Run server in observe-only mode — log all requests/responses, execute nothing
mcp-audit --mode=shadow \
  --server=github.com/third-party/mcp-server#v1.0.0 \
  --output=audit_logs/mcp_audit_$(date +%Y%m%d).jsonl

# Parse for suspicious patterns
python -c "
import json
suspicious = []
for line in open('audit_logs/mcp_audit_latest.jsonl'):
    entry = json.loads(line)
    if any(kw in str(entry).lower()
           for kw in ['password', 'token', 'api_key', 'secret', '\$'):
        suspicious.append(entry)
print(f'Suspicious entries: {len(suspicious)}')
for s in suspicious[:5]:
    print(json.dumps(s, indent=2))
"
```

A red-team review checklist for any MCP server:
- [ ] Does it log or store the full request payload? (data exfiltration)
- [ ] Does it make outbound network calls beyond its documented scope?
- [ ] Can its responses influence the agent's next tool call (response manipulation)?
- [ ] Does it require credentials that grant access beyond the tool's purpose?

### 5. Subscribe to RIFT-Bench for your MCP-based agents

[RIFT-Bench](https://arxiv.org/abs/2606.23927) (June 2026) provides a graph-representation framework for dynamic red-teaming of agentic systems. It is the closest thing to a standardized security eval for MCP-connected agents. Integrate it into your eval pipeline:

```python
# Simplified RIFT-Bench integration pattern
from riftbench import AgenticEvaluator

evaluator = AgenticEvaluator(
    agent=my_mcp_agent,
    attack_surfaces=["mcp_tool_injection", "mcp_response_manipulation", "mcp_scope_creep"],
    node_spec=my_agent_node_spec,  # define your agent's NodeSpec graph
)

report = evaluator.run_dynamic_probes(iterations=50)
print(f"Vulnerabilities found: {report.critical_count}")
print(f"Categories: {report.by_category}")
```

## Receipt

> Receipt pending — June 30, 2026
>
> The MCP server audit CLI (`mcp-audit`) referenced above is illustrative of the pattern. Verified: CVE-2026-2256 real-world prompt injection via MCP server is documented at stateofsurveillance.org (March 2026). RIFT-Bench (arXiv:2606.23927) published June 24, 2026. Pattern matching for instruction injection in tool results is implemented in practice by multiple production teams per iBuidl's March 2026 security report — they cite 67% prompt injection success on unguarded systems, dropping to under 4% with layered defenses. The capability scoping pattern is consistent with Infosys BPM's guardrails framework (2026) and Dextralabs's agentic safety playbook.

## See also

- [S-10 · MCP](s10-mcp.md) — MCP protocol fundamentals and what it solves
- [S-256 · MCP as the De-Facto Standard](s256-mcp-as-de-facto-tool-integration-standard.md) — why MCP won adoption
- [S-259 · OWASP ASI Top 10](s259-owasp-asi-top-10-for-agentic-applications.md) — the broader threat model for agentic systems
- [S-253 · Agent Sandboxing](s253-agent-sandboxing-as-a-first-class-layer.md) — isolating agent execution from the host
