# S-579 · MCP Skills and Capabilities — From Tool Catalog to Workflow Abstraction

An agent that needs to "rebook this customer's flight" must decompose that intent into a sequence of individual tool calls — search_flights, select_seat, apply_coupon, process_payment, send_confirmation_email — all manually wired in the prompt. MCP gave you a standard way to define each tool. It didn't give you a standard way to advertise the composed workflow. The 2026 MCP roadmap closes that gap with **Skills and Capabilities** — a higher-order abstraction where servers publish multi-tool workflows as first-class, discoverable units.

## Forces

- **Agents reason at workflow level; MCP exposes function-call level.** A booking agent doesn't think "call search_flights then select_seat then process_payment." It thinks "rebook the flight." The mismatch forces developers to pre-wire every workflow permutation into the agent's tool description, creating combinatorial schema bloat and brittle pre-configuration.

- **The tool catalog doesn't scale past 20 tools.** As MCP server ecosystems grow — 9,400+ public servers, 3–4× that internally in large enterprises — agents face increasingly large tool listings. The agent wastes context budget and reasoning tokens evaluating irrelevant tools. A flat tool list is a retrieval problem no agent solves well.

- **Workflow composition is bespoke today.** Teams solve "rebook flight" by baking the multi-tool sequence into the agent's system prompt or orchestration code. When the underlying MCP server changes a tool's schema, the workflow breaks silently — the agent adapts by working around it, and the workflow assumption rots without anyone noticing.

- **The MCP roadmap landed Skills in 2026.** The March 2026 MCP roadmap (AAIF/Linux Foundation) designates Skills and Capabilities as a priority work item. The concept: servers advertise *composable multi-tool workflows* with semantic descriptions, not just individual functions. Agents then reason about *capabilities* rather than *tool inventory*.

## The move

**1. Think in two layers: tools and skills.**

| Layer | What it is | Who defines it |
|---|---|---|
| **Tool** | Single function: `search_flights(origin, dest, date)` | MCP server developer |
| **Skill** | Composed workflow: `"rebook_flight" → [search → select → pay → confirm]` | Server advertises; agent discovers |

Skills sit above tools. A skill is a versioned, semantically described workflow that chains tools into an outcome. The agent sees both — it can still call tools directly, but it can also invoke skills as atomic capability units.

**2. Use capability descriptions, not tool lists.**

Instead of dumping every tool into the agent's context, publish a **capability manifest** at the MCP server level:

```json
{
  "capabilities": [
    {
      "id": "flight-rebooking",
      "description": "Re-books a customer's existing flight to a new date/route, "
                   + "preserving loyalty tier and seat preference",
      "prerequisites": ["customer_id", "original_booking_ref"],
      "outcomes": ["new_booking_ref", "confirmation_sent"],
      "version": "2.1.0"
    }
  ]
}
```

The agent sees only capabilities. It resolves which tools back each capability at plan time — not at configuration time. This decouples the agent's intent model from the tool implementation.

**3. Build the skill-to-tool resolver.**

When an agent invokes a skill, a resolver maps the skill ID to its tool chain and executes it:

```python
class SkillResolver:
    def resolve(self, skill_id: str, params: dict, ctx: AgentContext):
        skill_def = self.registry.get(skill_id)
        results = {}
        for step in skill_def.steps:
            tool_result = self.mcp_client.call(step.tool, {
                **step.params,
                **results  # pass prior outputs forward
            })
            results[step.output_key] = tool_result
            # If any step fails, rollback or escalate per skill_def.policy
        return skill_def.post_process(results)
```

The resolver handles parameter passing between steps, error propagation, and rollback — the agent just receives the composed outcome.

**4. Version skills independently from tools.**

A skill can pin to a specific tool version, enabling tool schema evolution without breaking existing workflows:

```json
{
  "id": "flight-rebooking",
  "tool_pins": {
    "search_flights": "^3.2.0",
    "process_payment": "^1.8.0"
  }
}
```

When a tool version drifts outside the pin range, the resolver raises a `CapabilityUnavailable` error — explicit failure instead of silent degradation.

**5. Add a capability-routing layer for large ecosystems.**

When you have 40+ MCP servers across the enterprise, add a lightweight **capability router** between agents and servers:

```
Agent intent
     ↓
Capability Router (semantic match: "rebook flight" → flight-rebooking@2.1.0)
     ↓
SkillResolver → MCP server chain
     ↓
Composed result back to agent
```

The router uses a lightweight embedding model over capability descriptions — not the full tool catalog — to route to the right skill. This collapses the tool-listing problem from O(servers × tools) to O(capabilities).

**6. Govern skill drift the same way you govern code.**

Treat skill definitions as configuration artifacts under version control:

- Pin skill versions in production deployments
- Diff skill definitions on MCP server updates — alert when a published skill's tool chain changes
- Require change-log entries for skill modifications (what workflows does this change touch?)
- Run integration tests for each affected skill when a backing tool updates

## When to use this

Reach for skills when:
- Agents frequently compose the same multi-tool sequences (rebook, onboard, refund, report)
- Your MCP ecosystem exceeds 15–20 tools total
- Multiple agents need the same workflow but can't share pre-wired prompts
- You need capability-level access control (not tool-level)

Skip skills when:
- Your agents use fewer than 5 tools total — the indirection overhead isn't worth it
- Workflows are one-off or highly context-specific (no reuse benefit)
- Your MCP server already bundles all related tools into a single "fat" tool

## Receipt

> Verified 2026-07-04 — MCP 2026 roadmap (AAIF, March 2026) defines Skills and Capabilities as priority work item. toloka.ai and tedt.org confirm: skills advertise "composable multi-tool workflows rather than individual tools" as a higher-level abstraction for agents. Enterprise MCP use cases (cdata.com, May 2026) report 40–60% faster workflow development with capability-level vs. tool-level integration. No existing handbook entry covers this abstraction layer — s269 covers tool abstraction, s280 covers server governance, s269 covers the tool level but not the skill level above it.

## See also

- [S-269 · MCP as the Tool-Abstraction Layer](s269-mcp-tool-abstraction-layer.md) — the level below skills
- [S-280 · MCP Server Governance](s280-mcp-server-governance.md) — governing the ecosystem skills live in
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — MCP vertical + A2A horizontal; skills sit inside the MCP layer
- [S-306 · MCP Tool Description Quality Is the Bottleneck](s306-mcp-tool-description-quality-is-the-bottleneck.md) — the human-authored descriptions that power capability routing
