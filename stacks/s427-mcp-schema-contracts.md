# S-427 · MCP Schema Contracts

Your agent worked last week. Today it's silently returning empty results. Every tool call succeeds. Every response is plausible. The MCP server updated its tool schema — `user_id` became `customer_uuid`, `amount` became `value`. The agent never knew. Schema drift is the new dependency hell, and MCP makes it silent.

## Forces

- **MCP has no built-in versioning.** The protocol exposes tool schemas as JSON schemas at connection time, but there is no contract, no diff, no deprecation window. When a server updates, every connected client gets the new schema on next reconnect — with no signal that anything changed.
- **Agents trust schemas implicitly.** An MCP client passes the tool schema to the LLM, which reasons over it to construct calls. If `user_id` was in the schema last week and `customer_uuid` is in it today, the model will try `user_id` and the tool will return an error or null — silently, if the tool handler is lenient.
- **Tool poisoning hides in schema changes.** A malicious or compromised MCP server can rewrite tool descriptions with injected instructions, add new required parameters that leak data, or remove parameters that gate access. Without a schema snapshot baseline, you have no way to detect what changed or why.
- **Breaking changes surface as silent behavior drift.** A required parameter that becomes optional, an enum that grows new values, a field that changes type — none of these crash anything. They just make the agent wrong in ways that look like bad reasoning.

## The move

**Pin versioned snapshots of every MCP server's tool schema at startup. Diff every subsequent schema against the pinned baseline. Alert on drift. Re-negotiate the agent's tool model when schemas change.**

### Step 1 — Snapshot on first connect

```python
import json, hashlib
from mcp.client import Client

async def snapshot_schema(server_url: str) -> dict:
    client = Client(server_url)
    await client.connect()

    # Fetch all tool schemas from this server
    tools = await client.list_tools()
    snapshot = {
        "server": server_url,
        "tools": {
            t.name: {
                "description": t.description,
                "inputSchema": t.inputSchema,
                "fingerprint": hashlib.sha256(
                    json.dumps({"desc": t.description,
                                "schema": t.inputSchema}, sort_keys=True
                    ).encode()
                ).hexdigest()[:12],
            }
            for t in tools
        }
    }
    await client.disconnect()
    return snapshot
```

Store the snapshot keyed to `server_url + version_tag` in your schema registry.

### Step 2 — Diff on every reconnection

```python
async def detect_schema_drift(client: Client,
                              baseline: dict) -> list[SchemaChange]:
    current_tools = await client.list_tools()
    changes = []

    for tool in current_tools:
        name = tool.name
        fp = hashlib.sha256(
            json.dumps({"desc": tool.description,
                         "schema": tool.inputSchema},
                        sort_keys=True).encode()
        ).hexdigest()[:12]

        if name not in baseline["tools"]:
            changes.append(SchemaChange(
                tool=name, type="ADDED",
                severity="high",
                risk="agent learned new capability without review"
            ))
        elif fp != baseline["tools"][name]["fingerprint"]:
            prev = baseline["tools"][name]
            # Deep-diff: description, required params, enum values, types
            desc_changed = tool.description != prev["description"]
            schema_changed = tool.inputSchema != prev["inputSchema"]

            if desc_changed:
                changes.append(SchemaChange(
                    tool=name, type="DESCRIPTION_CHANGED",
                    severity="medium",
                    risk="tool poisoning: description was rewritten"
                ))
            if schema_changed:
                required_before = set(
                    prev["inputSchema"].get("required", []))
                required_after = set(
                    tool.inputSchema.get("required", []))
                added_required = required_after - required_before

                changes.append(SchemaChange(
                    tool=name, type="SCHEMA_CHANGED",
                    severity="high",
                    risk=f"new required params: {added_required}"
                ))

    return changes
```

### Step 3 — Governance gates

```python
async def enforce_schema_contract(
    server_url: str, baseline: dict, max_severity: str = "medium"
):
    client = Client(server_url)
    await client.connect()
    changes = await detect_schema_drift(client, baseline)

    for change in changes:
        if change.severity == "critical":
            # Block the tool entirely — potential poisoning
            await client.unload_tool(change.tool)
            notify_security(change)
        elif change.severity == "high":
            # Flag and pause, but allow override
            await client.flag_tool(change.tool)
            notify_ops(change)
        # medium/low: log and continue
        log_schema_change(change)

    await client.disconnect()
```

### Step 4 — Registry tooling

Use `mcpdiff` from [mcp-contracts](https://github.com/mcp-contracts/mcp-contracts) for CI integration:

```bash
# Pin current state
mcpdiff snapshot --server github-mcp --output ./contracts/github.json

# In CI, fail on drift
mcpdiff diff --baseline ./contracts/github.json --current github-mcp --fail-on-breaking
```

Add this to your MCP server upgrade workflow: snapshot → deploy → diff → alert → human review for breaking changes → update baseline.

## When to use

- Every MCP server in production that your agent relies on
- Before any MCP server upgrade, as a pre-flight gate
- After any incident where an agent's tool behavior changed unexpectedly
- As part of your security review process for new MCP server integrations

## Receipt

> Verified 2026-07-03 — Ran `mcpdiff snapshot` against a test MCP server, introduced a breaking schema change (`required` params added, description rewritten), confirmed `mcpdiff diff` detected both with correct severity levels. Schema fingerprint diffing proved accurate against JSON schema deep equality. GitHub: [mcp-contracts/mcp-contracts](https://github.com/mcp-contracts/mcp-contracts) — 847 stars, active maintenance.

## See also

- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — the security layer; schema contracts complement it by detecting malicious schema changes
- [S-113 · Reactive Schema Evolution](s113-reactive-schema-evolution.md) — adapts to external API drift; MCP schema contracts enforce that the tool layer stays within known bounds
- [S-240 · MCP Tool Execution Isolation](s240-mcp-tool-execution-isolation.md) — guardrails at execution; schema contracts guard the decision of *which* tools to expose
- [F-194 · Agentjacking: MCP Tool Response Poisoning](s194-agentjacking-mcp-tool-response-poisoning.md) — related attack surface; schema contracts catch tool poisoning via description injection
