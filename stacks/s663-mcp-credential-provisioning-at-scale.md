# S-663 · MCP Credential Provisioning at Scale

You wired 12 MCP servers to your agent fleet. Now you have 12 servers × 8 agents × 3 environments = 288 credential sets scattered across developer laptops, CI runners, and agent runtimes. Nobody can audit them. Nobody can rotate them. When one server gets compromised, you have no idea which agents are exposed. The Model Context Protocol standardized *how* agents call tools — it left the auth story entirely to you.

## Forces

- **MCP crossed 110M monthly SDK downloads by early 2026** and is governed by the Agentic AI Foundation under the Linux Foundation. Adoption outpaced security hardening. A 2025 audit found nearly 2,000 publicly-exposed MCP servers, every one with zero authentication — not a developer failure, a protocol design choice (auth was explicitly out of scope in the MCP spec).
- **Credential sprawl compounds non-linearly.** 30 AI coding agents × 6 tools (GitHub, Jira, Confluence, Postgres, Slack, internal code review) = 180 credential sets, each representing a potential blast radius. Without a gateway, every agent carries every credential for every tool it *might* call — even if it never does.
- **Per-server auth is insufficient.** Giving an agent "access to the GitHub MCP server" grants it every tool the server exposes. Read-only `list_issues` sits beside `delete_repo`. Per-tool, per-agent RBAC is the required granularity.
- **Enterprise IdPs don't speak MCP natively.** Microsoft Entra doesn't support MCP's Dynamic Client Registration. A gateway control plane bridges that gap without replacing your existing identity infrastructure.
- **Manual credential rotation blocks agent autonomy.** Agents run continuously; revoking a credential kills in-flight tasks. Ephemeral, just-in-time credentials are the solution — but someone has to build the issuance and revocation pipeline.

## The Move

Deploy an **MCP Gateway** as a centralized auth and routing layer between your agent fleet and your MCP server ecosystem. The gateway owns four concerns:

### 1. Centralized Credential Vault

Store credentials once, route them dynamically. The gateway holds long-lived server credentials (rotated on schedule) and issues short-lived, scoped tokens to agents on demand.

```python
# Gateway: issue ephemeral tool-scoped token on agent request
from mcp_gateway import MCPCateway

gateway = MCPGateway(
    vault_url="https://vault.internal",
    idp_provider="entra",       # Okta, Auth0, Microsoft Entra
    rbac_policy_path="policy/mcp-tool-rbac.yaml"
)

# Agent authenticates once; gateway brokers per-tool tokens
async def agent_request(agent_id: str, tool_names: list[str]):
    # Verify agent has identity + role in IdP
    agent_identity = await gateway.verify_agent(agent_id)
    
    # Check RBAC: agent_role → allowed_tools
    allowed = gateway.filter_tools(agent_identity, tool_names)
    # denied_tools = set(tool_names) - set(allowed)
    
    # Issue scoped, short-lived token for allowed tools only
    token = await gateway.issue_ephemeral_token(
        agent_id=agent_id,
        tools=allowed,
        ttl_seconds=300,       # 5-minute token — dies fast
        mcp_server="github-production"
    )
    return {"mcp_access_token": token, "allowed_tools": allowed}
```

### 2. Tool-Level RBAC

Gateways enable the critical security control that per-server auth cannot: **tool-level permission scoping within a single server.** An agent gets `list_issues` but not `delete_repo`.

```yaml
# policy/mcp-tool-rbac.yaml
roles:
  code_review_agent:
    tools:
      github-production:
        allowed: [list_repos, list_issues, create_comment, list_pull_requests]
        denied: [delete_repo, push_force, transfer_repo]
    mcp_servers: [github-production, jira-standard]

  data_pipeline_agent:
    tools:
      postgres-prod:
        allowed: [select_only, list_tables]
        denied: [truncate, drop_table, modify_schema]
    mcp_servers: [postgres-prod]
    row_filter: "tenant_id = '{agent_tenant_id}'"   # data-plane isolation
```

### 3. Federated Identity (On-Behalf-Of Pattern)

Agents act under the *user's* identity, not a shared service account. The gateway maps agent sessions to user identity tokens from the IdP, enabling per-user audit trails.

```python
# On-behalf-of: agent operates as the authenticated user
async def tool_call_with_user_context(
    agent_id: str,
    user_idp_token: str,      # User's Entra/Okta token passed from frontend
    tool_name: str,
    params: dict
):
    # Gateway exchanges user token for scoped tool token
    user_claims = await gateway.idp_exchange(user_idp_token)
    # → user has: read_billing, write_orders, read_inventory
    
    if tool_name not in user_claims.allowed_tools:
        raise MCPAccessDenied(f"Tool {tool_name} not in user scope")
    
    # Tool call executes under user's identity → audit log shows who + which agent
    result = await gateway.forward_tool_call(
        tool_name, params,
        on_behalf_of=user_claims.email,
        agent_id=agent_id
    )
    return result
```

### 4. Gateway Deployment Topology

```
┌─────────────────────────────────────────────────────┐
│                   MCP Gateway                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │  AuthN   │  │  RBAC    │  │  Credential Vault │ │
│  │  (OAuth  │  │ (tool-   │  │  (short-lived     │ │
│  │   2.1 +  │  │  level)  │  │   tokens)        │ │
│  │   PKCE)  │  │          │  │                   │ │
│  └────┬─────┘  └────┬─────┘  └─────────┬─────────┘ │
│       │             │                   │            │
│       └─────────────┼───────────────────┘            │
│                     ▼                                │
│              ┌──────────────┐                        │
│              │  Audit Log   │  ← every tool call,    │
│              │  (immutable)  │    agent_id + user +  │
│              └──────────────┘    timestamp + result  │
└─────────────────────────────────────────────────────┘
        │                        │
   ┌────▼────┐               ┌────▼────┐
   │  MCP    │               │  MCP    │
   │ Server  │               │ Server  │
   │ GitHub  │               │ Postgres│
   │         │               │         │
   └─────────┘               └─────────┘
```

**Deployment model matters.** Cloud-hosted managed gateways (Bifrost, Composio, Obot) reduce time-to-production but route traffic through external infrastructure — a filter for healthcare, finance, and government. Self-hosted / VPC-deployed gateways preserve data sovereignty. Enforce this as a first configuration decision, not an afterthought.

### 5. Auth Standard Checklist for Evaluating a Gateway

| Capability | Minimum | Recommended |
|---|---|---|
| Auth protocol | API key rotation | OAuth 2.1 + PKCE |
| Identity | Static agent key | OIDC (Okta, Entra, Auth0) |
| Token type | Long-lived per-server | Short-lived, tool-scoped |
| RBAC granularity | Gateway-level | **Tool-level within server** |
| On-behalf-of | Not supported | Agent acts under user identity |
| Audit | None | Immutable log, agent_id + user + tool + result |
| IdP integration | None | Managed connector for your IdP |

## Receipt

> Verified 2026-07-06 — MCP crossed 110M monthly SDK downloads (Composio, Dec 2025). 2025 security audit: 2,000 MCP servers publicly exposed, zero auth (AgentMarketCap, Apr 2026). Bifrost, Composio, Obot, Strata provide MCP gateway solutions. MCP Gateway market projected at $10B by 2026 (AgentMarketCap). Auth explicitly out-of-scope in MCP spec (Composio enterprise guide, Jun 2026). Example gateway code is representative; Bifrost virtual-key pattern and Obot Enterprise-Managed Authorization (EMA) provide the production reference implementations.

## See also

- [S-280 · MCP Server Governance](stacks/s280-mcp-server-governance.md) — registry, schema drift, CVE propagation
- [S-313 · Agent Credential Lifecycle Security](stacks/s313-agent-credential-lifecycle-security.md) — issuance, rotation, revocation as first-class lifecycle
- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](stacks/s420-agent-identity-governance-the-AI-principal-paradigm.md) — NHI governance, IAM gap for non-human actors
- [S-625 · MCP Has Won the Tool-Calling Standard War — Now the Security Bill Comes Due](stacks/s625-mcp-the-standard-that-won-and-the-security-bill-coming-due.md) — MCP adoption vs. security hardening gap
