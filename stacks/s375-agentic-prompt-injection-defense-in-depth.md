# S-375 · Agentic Prompt Injection: Defense-in-Depth for Production

An AI agent processes a scraped web page, an email, or a document — and acts on instructions the attacker smuggled inside. The agent deletes files, emails clients, or forwards credentials. This is not a hypothetical. Prompt injection has been OWASP LLM01 — the #1 vulnerability in LLM applications — for three consecutive years. In production agentic deployments, the blast radius is an order of magnitude larger than in chatbots: agents write files, call APIs, browse the web, execute code. A 2026 RSAC finding confirmed that 73% of production AI deployments are vulnerable to some form of injection attack, while only 29% of organizations feel prepared to secure them.

## Forces

- **Agents are read-write; chatbots are read-only.** The same injected instruction that manipulates a chatbot's output compromises a code-execution agent's filesystem, cloud credentials, or customer data
- **Environmental inputs are untrusted but trusted by default.** Web pages, emails, documents, and tool responses all enter the context window without verification — and LLMs process all tokens equally, with no native concept of "instruction vs. data"
- **Traditional input validation doesn't work.** Regex patterns and content filters fail because adversarial instructions can be embedded in natural language, encoded indirectly, or hidden across multiple turns
- **The attacker has a larger surface than the defender.** Multi-turn attacks achieved 92% success against 8 open-weight models; indirect injection via RAG poisoning requires only five carefully crafted documents

## The move

Treat prompt injection as a **security boundary problem**, not a content moderation problem. The goal is not to filter malicious instructions — it is to prevent instructions from crossing the boundary where they carry authority. Defense-in-depth means seven independent layers; no single layer is sufficient, but together they raise the cost of successful exploitation beyond practical reach.

### Layer 1 — Input Separation (Structural)

Use structural delimiters that make the boundary between user/environmental content and system instructions explicit and machine-parseable.

```python
[language=python]
import re

class SeparatedInput:
    """Wrap external content in structural markers the model learns to distrust."""

    SYSTEM_PREFIX = "<|trusted|>"
    USER_PREFIX = "<|external|>"   # content from untrusted sources
    SUFFIX = "<|/external|>"

    @classmethod
    def wrap(cls, content: str, source: str = "user") -> str:
        if source == "external":
            return f"{cls.USER_PREFIX}{content}{cls.SUFFIX}"
        return f"{cls.SYSTEM_PREFIX}{content}"

    @classmethod
    def extract_external(cls, text: str) -> list[str]:
        """Pull any content that leaked outside its wrapper."""
        matches = re.findall(r"<\|external\|>(.*?)<\|/external\|>", text, re.DOTALL)
        return matches
```

The model learns through fine-tuning or ICL that content inside `<|external|>` wrappers is informational, not directive. This is not a security control on its own — it is a structural signal that layers 2-7 can enforce.

### Layer 2 — Capability-gated Tool Calls (Enforcement)

Every tool call is a potential injection pivot. Gate them with explicit capability checks, not trust.

```python
[language=python]
from enum import Flag, auto
from dataclasses import dataclass, field
from typing import Callable
import hashlib

class Capability(Flag):
    READ_FILE    = auto()
    WRITE_FILE   = auto()
    EXECUTE_CODE = auto()
    NETWORK     = auto()
    SECRETS     = auto()   # access to credentials, API keys

@dataclass
class AgentIdentity:
    id: str
    capabilities: Capability
    session_key: str  # derived from session, not stored plaintext

@dataclass
class ToolCall:
    tool_name: str
    args: dict
    caller: AgentIdentity
    intent: str = ""  # model-provided rationale — not trusted

TOOL_CAPABILITIES: dict[str, Capability] = {
    "read_file":   Capability.READ_FILE,
    "write_file":  Capability.WRITE_FILE,
    "send_email":  Capability.NETWORK | Capability.SECRETS,
    "run_sql":     Capability.SECRETS,
    "exec_bash":   Capability.EXECUTE_CODE,
}

def authorize(call: ToolCall) -> bool:
    required = TOOL_CAPABILITIES.get(call.tool_name, Capability(0))
    granted = call.caller.capabilities
    # Capability can only grow via explicit human approval, never via LLM instruction
    if required & granted != required:
        raise PermissionError(
            f"Agent {call.caller.id} lacks {required} required for {call.tool_name}"
        )
    return True
```

Key rule: the LLM cannot grant itself capabilities. Any instruction that attempts to escalate privileges must be caught at this layer before it reaches the tool.

### Layer 3 — MCP Tool Surface Hardening

MCP (covered in [S-10](s10-mcp.md) and [S-365](s365-mcp-supply-chain-from-npx-to-production-catalog.md)) is the dominant new attack surface. Three specific hardening measures:

```python
[language=python]
# 1. Capability Enumeration Prevention
# Log and flag MCP tool listing requests — legitimate tools don't enumerate randomly
async def mcp_enumeration_guard(requested_tools: list[str], caller: AgentIdentity):
    suspicious = (
        len(requested_tools) > 5 or
        "mcp__capabilities__*" in str(requested_tools)
    )
    if suspicious:
        await audit_log.alert("MCP_ENUMERATION", caller_id=caller.id, tools=requested_tools)
        raise SecurityError("Suspicious MCP tool enumeration blocked")

# 2. Tool Description Validation
# Reject tools whose descriptions contain instruction-like content
INJECTION_PATTERNS = [
    r"ignore (all )?(previous|above|prior) instructions",
    r"system prompt",
    r"<\|.*?\|>",  # delimiter injection
    r"do not check",
    r"bypass",
]

def validate_tool_description(description: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, description, re.IGNORECASE):
            return False  # flagged for review
    return True

# 3. Least-Privilege MCP Scoping
# Each MCP server gets a scoped permission set; no wildcard access
MCP_SERVER_SCOPES: dict[str, Capability] = {
    "filesystem":   Capability.READ_FILE | Capability.WRITE_FILE,
    "email":        Capability.NETWORK,
    "database":     Capability.SECRETS,
    "web_browser":  Capability.NETWORK | Capability.READ_FILE,
    # No MCP server ever gets EXECUTE_CODE or broad SECRETS
}
```

### Layer 4 — Structural Output Validation

Parse and validate tool calls before execution. If the model generates something that looks like a direct instruction rather than a tool call, flag it.

```python
[language=python]
import json

class OutputValidator:
    """
    Reject text outputs that contain direct instructions — these indicate
    the model may have acted on injected content rather than staying in tool-call mode.
    """
    DIRECTIVE_PATTERNS = [
        r"^(delete|remove|forward|send|execute|grant|revoke)\s+\w+\s+",
        r"^ignore (all )?instructions",
        r"^disregard",
        r"set.*password",
        r"grant.*access",
    ]

    @classmethod
    def validate(cls, output: str, expected_mode: str = "tool_call") -> bool:
        if expected_mode == "tool_call":
            try:
                # If it looks like a tool call, it must be valid JSON
                parsed = json.loads(output)
                return True
            except json.JSONDecodeError:
                pass

        for pattern in cls.DIRECTIVE_PATTERNS:
            if re.match(pattern, output.strip(), re.IGNORECASE):
                return False  # direct instruction — not a tool call

        return True
```

### Layer 5 — Zero-Trust Agent Identity (A2A v1.0)

With A2A v1.0 (April 9, 2026), agents gain cryptographically signed identity via **Signed Agent Cards**: JWT-signed, JCS-canonicalized identity primitives embedded in every agent-to-agent message. This closes the audit gap — "which agent authorized this action?" — at the protocol layer.

```python
[language=python]
import jwt
from datetime import datetime, timedelta

class SignedAgentCard:
    def __init__(self, agent_id: str, private_key_pem: str, public_key_url: str):
        self.agent_id = agent_id
        self.private_key = private_key_pem
        self.public_key_url = public_key_url

    def sign_message(self, payload: dict) -> str:
        """Sign a tool call or handoff message with agent's private key."""
        payload["agent_id"] = self.agent_id
        payload["timestamp"] = datetime.utcnow().isoformat()
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    @classmethod
    def verify(cls, token: str, public_key_url: str) -> dict:
        """Any receiving agent can verify using the public key from the Agent Card."""
        # In production: fetch key from public_key_url, validate signature + expiry
        return jwt.decode(token, options={"verify_signature": False})
```

No A2A message should be acted upon without verified signature. This also enables non-repudiable audit trails: every action traces back to a specific agent with a specific identity.

### Layer 6 — Blast Radius Containment (Compensation + Sandbox)

From [S-361](s361-agent-stack-stratification-sandboxing-infrastructure-prerequisite.md): code execution agents run in ephemeral microVMs (E2B, Modal, Firecracker). Assume compromise is inevitable and minimize what an injected instruction can do.

```python
[language=python]
# From S-001-style compensation keys — apply to security domain
AGENT_SCOPED_SECRETS = {
    # Each agent gets only the credentials it needs for its specific task
    "code_agent_001":  {"github_token": "ghp_xxx_limited_repo"},  # repo-scoped, not full org
    "email_agent_002": {"smtp": "real but rate-limited"},
    "data_agent_003": {"db": "read_only connection string"},
}

EPHEMERAL_SECRETS = {
    # Time-limited credentials issued per session, auto-revoked on completion
    "session_creds": {"ttl_seconds": 3600, "auto_revoke": True}
}
```

Compensation actions (from the [I-001 three-key model](https://github.com/badlandslabs/handbook/tree/main/stacks)) apply here: if an injected instruction caused unauthorized writes, the compensation key drives the rollback. The blast radius is bounded by the agent's scoped credential set.

### Layer 7 — Human-in-the-Loop Gate (For High-Risk Actions)

For actions that cross significant trust boundaries — deleting records, sending external emails, modifying access controls — require human confirmation before execution. This is not a failure of automation; it is a calibrated control.

```python
[language=python]
HIGH_RISK_ACTIONS = {"delete", "send_external", "grant_access", "revoke_access"}

class HumanApprovalGate:
    @classmethod
    def requires_approval(cls, tool_name: str, args: dict) -> bool:
        return tool_name in HIGH_RISK_ACTIONS or any(
            k in args for k in ["destination_external", "grant_role"]
        )

    @classmethod
    async def request_approval(cls, call: ToolCall) -> bool:
        # Queue for human review; block execution until approved
        await approval_queue.enqueue(call)
        return False  # caller must wait
```

## Receipt

> Verified 2026-07-02 — Sources: Zylos Research (2026-05-16), AgDex (2026-04-27), GetMaxim/Bifrost (2026-06), OWASP LLM Top 10 LLM01:2025, RSAC 2026 findings. Code patterns are structural illustrations. Layer 5 (A2A v1.0 Signed Agent Cards) confirmed via A2A Protocol v1.0 announcement (a2a-protocol.org, 2026-04-09) and AgentMarketCap (2026-04-18). GitHub Copilot CVE-2025-53773 (CVSS 9.6, remote code execution via malicious instructions in fetched content) cited per Bifrost research.

## See also

- [S-355 · Agent Autonomy Levels (Bounded Autonomy)](s355-agent-autonomy-levels-bounded-autonomy.md) — L3+ escalation gates and the read-to-write boundary
- [S-360 · Governance Decay](s360-governance-decay-the-silent-safety-erosion-pattern.md) — constraint pinning and the safety erosion mechanism
- [S-361 · Agent Stack Stratification](s361-agent-stack-stratification-sandboxing-infrastructure-prerequisite.md) — sandboxing as blast radius containment
- [S-365 · MCP Supply Chain](s365-mcp-supply-chain-from-npx-to-production-catalog.md) — MCP-specific attack surface and artifact pinning
- [S-368 · Agent Span Tracing](s368-agent-span-tracing-observable-agent-sessions.md) — observability as the prerequisite for detection
