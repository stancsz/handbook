# S-280 · MCP Server Governance

Your MCP ecosystem grew from 3 servers to 23 in six months. Anyone on the team can spin up a new server and attach it to production agents. One server has a CVE. One server silently changed its output schema and 4 agents started returning wrong data. Nobody knows which agents use which servers, who approved them, or when they were last updated. The MCP Registry gave you a place to publish servers — it didn't give you a system to govern them.

## Forces

- **MCP's low friction cuts both ways.** Publishing a server takes minutes; auditing 40 servers across 15 agents takes days. The same developer experience that makes MCP powerful makes it a governance attack surface.
- **Schema drift propagates silently through agent pipelines.** An MCP server changes a response field name. The agent's tool-call parsing quietly breaks. The user gets garbage. No error is raised because the agent worked around it.
- **CVE propagation is faster than patch cycles.** S-261 documented the supply-chain attack surface. In production, the question is not just "is this server malicious?" but "is this server patched?" and "which agents depend on it right now?"
- **Enterprise compliance requires tool-layer audit trails.** SOC 2, ISO 27001, and the EU AI Act all have requirements for knowing what tools your AI systems can access, who authorized them, and what data they touched.
- **The MCP Registry solved discovery, not governance.** Public registries list servers; they don't track your internal fleet, server versions, or agent-to-server dependency graphs.

## The move

MCP server governance has four layers: **inventory**, **approval**, **versioning**, and **runtime enforcement**. Implement them as a controller pattern — automated, not manual.

### 1. Server Inventory & Dependency Graph

Every MCP server in your fleet must be registered in a central store that tracks: server name, version, owner team, schema fingerprint (hash of input/output types), and which agents currently consume it.

```python
from dataclasses import dataclass, field
from typing import Set
import hashlib, json

@dataclass
class MCPServer:
    name: str
    version: str
    owner_team: str
    schema_fingerprint: str          # SHA-256 of JSON input/output schemas
    agents: Set[str] = field(default_factory=set)

    @classmethod
    def from_manifest(cls, manifest_path: str) -> "MCPServer":
        """Derive fingerprint from a server's manifest."""
        with open(manifest_path) as f:
            meta = json.load(f)
        schema_bytes = json.dumps(meta.get("schemas", {}), sort_keys=True).encode()
        return cls(
            name=meta["name"],
            version=meta["version"],
            owner_team=meta["owner_team"],
            schema_fingerprint=hashlib.sha256(schema_bytes).hexdigest()[:16],
        )

# Detect schema drift: compare registered fingerprint vs. current on-disk
def check_schema_drift(server: MCPServer, manifest_path: str) -> bool:
    current = MCPServer.from_manifest(manifest_path)
    return current.schema_fingerprint != server.schema_fingerprint
```

Run this check on every CI push. If the fingerprint changes, block the merge and alert the owner team — schema drift is a production incident waiting to happen.

### 2. Approval Workflow

Treat MCP servers like packages: they need approval before production use.

```python
from enum import Enum

class ServerApprovalStatus(Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"

class MCPServerRegistry:
    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._status: dict[str, ServerApprovalStatus] = {}
        self._audit_log: list[dict] = []

    def propose(self, server: MCPServer, approver: str, risk_level: str = "low"):
        """New server enters proposed state. Requires review before use."""
        self.servers[server.name] = server
        self._status[server.name] = ServerApprovalStatus.PROPOSED
        self._audit_log.append({
            "action": "proposed",
            "server": server.name,
            "by": approver,
            "risk_level": risk_level,
        })

    def approve(self, name: str, reviewer: str, conditions: list[str] | None = None):
        if self._status.get(name) != ServerApprovalStatus.PROPOSED:
            raise ValueError(f"{name} must be proposed before approval")
        self._status[name] = ServerApprovalStatus.APPROVED
        self._audit_log.append({
            "action": "approved",
            "server": name,
            "by": reviewer,
            "conditions": conditions or [],
        })

    def revoke(self, name: str, reason: str, revoked_by: str):
        self._status[name] = ServerApprovalStatus.REVOKED
        self._audit_log.append({
            "action": "revoked",
            "server": name,
            "reason": reason,
            "by": revoked_by,
        })
        # Alert all agents that depend on this server
        for agent in self.servers[name].agents:
            self._notify_agent_owner(agent, name, reason)
```

Gate agent startup so an agent can only attach to APPROVED servers. Reject at runtime with a clear error — don't let a degraded or revoked server become a silent failure mode.

### 3. CVE Response Playbook

When a CVE hits a dependency in an MCP server, you need a circuit breaker, not a Slack message.

```python
import asyncio, httpx
from datetime import datetime, timedelta

class MCPCVEBreaker:
    def __init__(self, registry: MCPServerRegistry):
        self.registry = registry
        self._nvd_base = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    async def check_cve(self, server_name: str, cve_id: str, cvss_min: float = 7.0):
        """Poll NVD. If CVSS >= threshold, revoke server and notify agents."""
        async with httpx.AsyncClient() as client:
            r = await client.get(self._nvd_base, params={"cveId": cve_id}, timeout=10)
            r.raise_for_status()
            cve = r.json()["vulnerabilities"][0]["cve"]
            metrics = cve.get("metrics", {})
            cvss_v31 = metrics.get("cvssMetricV31", [])
            if not cvss_v31:
                return  # No CVSS 3.1 data yet
            score = cvss_v31[0]["cvssData"]["baseScore"]
            if score >= cvss_min:
                self.registry.revoke(
                    server_name,
                    reason=f"CVSS {score} CVE-{cve_id}: {cve['descriptions'][0]['value']}",
                    revoked_by="cve-breaker",
                )
                print(f"[CRITICAL] Revoked {server_name} — {cve_id} CVSS {score}")

    async def sweep_cves(self, cve_ids: list[tuple[str, str]]):
        """Check multiple (server_name, cve_id) pairs concurrently."""
        tasks = [
            self.check_cve(server, cve)
            for server, cve in cve_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
```

Run this as a nightly cron job. Set CVSS threshold based on your risk tolerance — for data-access servers, even CVSS 5.0 warrants a review.

### 4. Runtime Enforcement

At startup, validate the full agent-to-server dependency graph against the registry:

```python
def validate_agent_config(agent_name: str, requested_servers: list[str], registry: MCPServerRegistry) -> list[str]:
    """
    Returns list of errors. Empty list means the agent can start safely.
    """
    errors = []
    for server_name in requested_servers:
        status = registry._status.get(server_name)
        if status is None:
            errors.append(f"[{agent_name}] {server_name} is not registered")
        elif status == ServerApprovalStatus.REVOKED:
            errors.append(f"[{agent_name}] {server_name} is REVOKED — cannot start")
        elif status == ServerApprovalStatus.DEPRECATED:
            errors.append(f"[{agent_name}] {server_name} is DEPRECATED — migrate by {get_deadline(server_name)}")
        elif status == ServerApprovalStatus.PROPOSED:
            errors.append(f"[{agent_name}] {server_name} is not yet APPROVED")
    return errors
```

Wrap this in the agent's initialization. Treat a non-empty error list as a startup failure with a structured error message — don't fall back to permissive mode.

## Receipt

> Receipt pending — July 1, 2026

## See also

- [S-256 · MCP as the De-Facto Agent Tool-Integration Standard](s256-mcp-as-de-facto-tool-integration-standard.md) — the protocol foundation this governance layer extends
- [S-261 · MCP Security Attack Surface](s261-mcp-security-attack-surface.md) — CVE and supply-chain context that drives the CVE breaker
- [S-240 · MCP Tool Execution Isolation](s240-mcp-tool-execution-isolation.md) — runtime isolation, complementary to governance controls
