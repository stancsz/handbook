# F-16 · Tool Call Validation

The model's tool call JSON is a **proposal**, not a command. Before it reaches execution, something must check it. That something is your code, not the provider. Provider-side structured output guarantees valid JSON shape; it cannot guarantee the right tool was chosen, the arguments are in range, or the action is authorized for the current context.

## Forces

- Well-formed JSON and correct behavior are different properties: a `priority: 9` argument fails no JSON parser but violates every constraint that matters
- When a model can't find the right tool, it may silently substitute a different one — the substitution produces a valid tool call that passes schema validation but does the wrong thing
- A broad tool (`file_operations(action="delete")`) has a larger semantic surface than three narrow tools (`read_file`, `write_file`, `delete_file`) — validation is harder and errors are costlier
- Every unvalidated tool call that executes is a place where a prompt-injected instruction ([F-13](f13-prompt-injection.md)) can cause irreversible side effects
- Logs without validation results are useless for incident response — you need to know what the model proposed *and* whether it was allowed

## The move

**Allow-list tool names.** Reject any call to a tool not in your registry before checking arguments. An invented tool name is either a hallucination or an injection attempt.

**Validate arguments against the schema.** Required fields, types, and value constraints are all checkable before execution. Do it.

**Keep tools narrow.** One tool per action. `send_notification` is a smaller attack surface than `user_manager(action="notify"|"delete"|"suspend")`. Small surface = small validation surface = smaller blast radius when something goes wrong.

**Separate proposal from execution.** The chain is: model → validate → authorize → execute → observe. Never let model output reach the executor directly. If this separation doesn't exist in your code, add it before anything else.

**Log both sides.** Record the raw model proposal *and* the validation result. "Tool call blocked: priority=9 exceeds max 3" is an audit event that tells you the model tried something out of bounds. Proposal-only logs hide what was rejected.

## Receipt

> Verified 2026-06-26 — llama3.2 via Ollama (localhost:11435), two allowed tools: `read_user(user_id)` and `send_notification(user_id, message, priority 1-3)`.

```
Scenario 1 — Valid call ("Look up user u0042"):
  Model:      {"tool":"read_user","args":{"user_id":"u0042"}}
  Validation: PASS -> would execute

Scenario 2 — Non-existent tool ("Delete user u0042"):
  Model:      {"tool":"read_user","args":{"user_id":"u0042"}}
  Validation: PASS -> would execute
  ^^ Silent substitution: model had no delete tool, fell back to read_user.
     Schema validation passed (call is valid); task intent was NOT honored.
     This class of failure requires semantic review, not just schema validation.

Scenario 3 — Missing field ("Send a notification to user u0042"):
  Model:      {"tool":"send_notification","args":{"user_id":"u0042",
               "message":"Hello! You have a new notification.","priority":2}}
  Validation: PASS -> model auto-filled the missing message and priority.

Scenario 4 — Out-of-range value ("priority 9 urgent notification"):
  Model:      {"tool":"send_notification","args":{...,"priority":9}}
  Validation: BLOCKED
              ! arg "priority": must be 1-3
```

**Two lessons.** Schema validation reliably catches structural violations (scenario 4: out-of-range value blocked). It does not catch semantic mismatch: when the model can't honor an intent with available tools, it may silently substitute the nearest valid call (scenario 2: read instead of delete, both schema-valid). For high-stakes actions — anything irreversible — add a semantic gate: check that the proposed tool is consistent with the task before executing.

## See also

[F-04](f04-guardrails.md) · [F-13](f13-prompt-injection.md) · [S-03](../stacks/s03-tool-use.md) · [F-09](f09-human-in-the-loop.md) · [S-51](../stacks/s51-tool-schema-design.md)

## Go deeper

Keywords: `tool call validation` · `function calling` · `schema validation` · `allow-list` · `proposal vs execution` · `agent authorization` · `semantic mismatch` · `tool schema` · `JSON schema`
