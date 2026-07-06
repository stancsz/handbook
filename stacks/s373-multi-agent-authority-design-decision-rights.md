# S-373 · Multi-Agent Authority Design — Who Gets to Decide

Multi-agent systems fail not from bad models but from ungoverned authority. When two agents can both propose, both block, and neither can override, you get verbose non-decisions and race conditions that look like intelligence but resolve nothing. The teams shipping reliable agentic systems have solved the authority problem first — and the pattern is almost never consensus.

## Forces

- **Consensus is a bad protocol for async, unequal agents.** Shared conversation threads where every agent can propose and debate produce verbose output, last-word wins behavior, and agents that rubber-stamp whatever was said most recently.
- **Adding more agents compounds coordination cost, not just capability.** Each new agent introduces another authority claim. Without an explicit hierarchy, the system defaults to emergent, unpredictable power dynamics.
- **The decision of which agent *can* versus which agent *should* is rarely explicit.** Most systems conflate "has access to a tool" with "is authorized to trigger it." These need to be separate concerns.
- **Context cost creates hierarchy whether you design for it or not.** The agent with the longest context budget becomes the de facto decision-maker by default — not by intent.

## The move

**Design authority explicitly before you design capabilities.** Every agent needs a clear answer to three questions: Can it propose? Can it block? Can it override a block?

- **Veto-only agents** — some agents can only raise flags, never make calls. This removes the consensus problem entirely. The decider never needs to convince the blocker; the blocker only needs a reason to stay silent.
- **Explicit blocking rights, not implicit debate rights.** A "critique" agent that raises concerns in a thread is not a blocker — it's noise. A blocker needs a mechanism to halt progress until its concern is resolved, not a place to add another comment.
- **Asymmetric context budgets as authority proxies.** Give the decision-maker agent a larger context window than the advisors. The advisor can't out-argue what it can't see.
- **Prediction markets beat voting.** When agents bet against each other's outputs (assigning confidence scores or stake), the aggregate reliably beats majority vote. PAI Family runs this pattern across 13 agents.
- **Separation of CEO, Architect, Builder** — one agent sets direction and delegates, one agent checks feasibility, one agent executes. Each role has a single override condition. The CEO overrides the Architect on priority; the Architect overrides the Builder on feasibility; the Builder has no override.
- **Heartbeat coordination over real-time threads.** Agents that check a shared work queue on a schedule and emit results to it are more reliable than agents that wait for responses in a shared conversation. Async by default; sync only when the protocol requires it.

## Evidence

- **HN Ask thread (2025):** A team running 13 specialized agents (PAI Family) for research, finance, content, strategy, critique, and psychology — agents collaborate, raise flags, and bet against each other on a prediction market. Found that consensus failed in async; switched to "one agent blocks, one agent decides." — [https://news.ycombinator.com/item?id=47270020](https://news.ycombinator.com/item?id=47270020)
- **HN comment (2025):** Developer describing a 3-role Claude Code setup (CEO, Architect, Builder) where each role has a tagged permission pattern and explicit delegation rules. The CEO is restricted to coordination-only tools; the Architect owns feasibility; the Builder executes. — [https://news.ycombinator.com/item?id=47245373](https://news.ycombinator.com/item?id=47245373)
- **Opensoul Show HN (2025):** A 6-agent marketing agency stack with explicit role hierarchy — Director (strategy + team coordination) delegates to Strategist, Creative, Producer, Growth Marketer, and Analyst. Each agent runs on scheduled heartbeats checking a shared work queue, not a shared thread. — [https://news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615)

## Gotchas

- **"Everyone can propose" feels fair but produces the worst decisions.** Equality of voice in agent systems is not equivalent to equality of authority. Unstructured debate converges on the most recently spoken agent, not the most correct one.
- **Adding a critique agent without a blocking mechanism makes things worse.** The critique agent adds latency, generates verbose disclaimers, and changes nothing because nothing forces the primary agent to respond to the critique.
- **The authority model you design at 3 agents won't survive at 13.** Plan for a second authority layer (meta-agents that coordinate sub-groups) before you hit the scale where coordination breaks down.
- **Fire-and-forget spawning feels scalable but loses authority traceability.** If you can't reconstruct which agent made which decision and why, you can't audit or course-correct. File-based inbox persistence (append-only JSONL) is the minimum viable audit trail.
