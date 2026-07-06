# S-365 · MCP Supply Chain: From `npx` to Production Catalog

Your agent developer runs `npx @some-mcp-server` and the tool is live. Works great in dev. In production, you've shipped an unversioned binary from an unverified registry, with no artifact digest, no vulnerability scan, and no audit trail. JFrog detected active exploits against unpatched MCP servers in Q1 2026. Kong MCP Registry and Cisco/CrowdStrike are now treating MCP server catalogs as production artifacts with full SLSA provenance, signed digests, and CI promotion gates. The gap between "it works" and "it's secure" is your supply chain.

## Forces

- **`npx`/`uvx` resolves to whatever the registry serves right now.** No version pin, no hash verification, no SBOM. A malicious registry redirect or a compromised package silently breaks your agent's trust model without any CI failure.
- **MCP servers aggregate credentials across multiple systems.** A single server that connects to email, CRM, and database tools is a single point of credential aggregation. JFrog's MCP Security analysis (March 2026) found 43% of MCP servers contain command injection vulnerabilities — and a compromised server uses *your* credentials.
- **Production hardening and developer ergonomics are in tension.** The secure path (signed artifacts, CI gates, catalog promotion) feels heavyweight compared to `npx`. The fix is making the secure path the default, not an afterthought.
- **Protocol-level controls don't cover artifact-level controls.** MCP's authorization model (OAuth 2.1, audience-bound tokens) protects runtime access but does nothing for the artifact integrity problem — what's actually running on your infrastructure.

## The move

**Phase 1 — Pin and Hash-Lock in CI**

```bash
# Fetch and pin artifact hash at build time
ARTIFACT_URL=$(npm view @my-org/secret-mcp-server dist.tarball)
HASH=$(npx hash-artifact "$ARTIFACT_URL" --algo sha256)
echo "$ARTIFACT_URL $HASH" >> .mcp-servers/sapproved-hashes.txt

# In production: verify hash before running
curl -fsSL "$ARTIFACT_URL" | sha256sum --check <<< "$HASH"
```

Never `npx run` an MCP server without a pinned hash. Store approved hashes in a secrets manager, not in source.

**Phase 2 — CI Build and SBOM Generation**

```dockerfile
# Dockerfile.mcp-server (for self-hosted servers)
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
RUN npm run build

FROM node:20-alpine AS scan
COPY --from=build /app/dist /dist
# Scan for CVEs before publishing
RUN npm audit --audit-level=moderate || true
RUN npx syft /app -o spdx-json > /sbom.spdx.json

FROM node:20-alpine
COPY --from=build /app/dist /app
COPY --from=scan /sbom.spdx.json /sbom.spdx.json
ENTRYPOINT ["node", "/app/index.js"]
```

For third-party servers you can't rebuild, pin the Docker image digest instead of the tag:

```yaml
# kubernetes/mcp-server.yaml
spec:
  containers:
    - name: email-mcp
      image: docker.io/org/mcp-email:v1.2.3@sha256:abc123...  # digest-pinned
      imagePullPolicy: Always
```

**Phase 3 — Catalog Governance Gate**

```python
# mcp_catalog/approve.py
import hashlib, json
from dataclasses import dataclass

@dataclass
class MCPServer:
    name: str
    version: str
    digest_sha256: str
    sbom_path: str | None
    approved_by: str
    cvss_score: float | None = None

    def is_approved(self) -> bool:
        if self.cvss_score is not None and self.cvss_score >= 7.0:
            return False  # Block HIGH/CRITICAL CVEs
        return bool(self.digest_sha256 and self.approved_by)

# Promotion gate: only catalog-approved servers can be registered
def register_server(server: MCPServer, catalog_path: str) -> None:
    if not server.is_approved():
        raise PermissionError(
            f"Server {server.name}@{server.version} not approved. "
            f"CVSS={server.cvss_score}, digest={'<missing>' if not server.digest_sha256 else 'ok'}"
        )
    # Append to approved catalog (managed in GitOps workflow)
    ...

# Example: blocking an unapproved server
unpatched = MCPServer(
    name="legacy-email-mcp",
    version="1.0.0",
    digest_sha256="sha256:def456",
    sbom_path=None,
    approved_by="",
    cvss_score=9.1,
)
unpatched.is_approved()  # False — blocks registration
```

**Phase 4 — Runtime Verification**

```python
import subprocess, hashlib

def verify_and_launch(server_manifest: dict) -> subprocess.Popen:
    # 1. Verify digest matches approved catalog entry
    digest = compute_sha256(server_manifest["artifact_path"])
    approved = get_catalog_digest(server_manifest["name"])
    if digest != approved:
        raise SecurityError(f"Digest mismatch for {server_manifest['name']}: expected {approved}, got {digest}")

    # 2. Enforce capability scope — server only gets the tools it needs
    allowed_tools = get_tool_allowlist(server_manifest["name"])
    return launch_with_capabilities(server_manifest, allowed_tools=allowed_tools)
```

Key principles: verify before launch, scope capabilities to least-privilege, log every server registration event to your SIEM.

## Receipt

> Verified 2026-07-02 — Research synthesized from JFrog MCP Security analysis (March 2026: 43% of MCP servers vulnerable, CVSS 7.3–9.6), Kong MCP Registry documentation, Cisco/CrowdStrike MCP governance frameworks, and OBOT.ai's CI pipeline hardening guide. No live benchmark run performed — receipts reflect published industry data. Kong MCP Registry and JFrog MCP Security offerings are live in 2026.

## See also
- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — protocol-level hardening complement
- [S-261 · MCP Security — The Attack Surface You Inherited](s261-mcp-security-attack-surface.md) — credential aggregation risk
- [S-359 · MCP Security and the Agent Protocol Convergence](s359-mcp-security-and-agent-protocol-convergence.md) — protocol landscape context
