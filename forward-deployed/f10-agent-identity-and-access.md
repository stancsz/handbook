# F-10 · Agent Identity and Access

How an agent proves who it is and gets *only* the access it needs. The defense under the cross-agent privilege-escalation failure ([F-05](f05-agent-failure-taxonomy.md)) and the delegation-trust gap A2A leaves open ([S-14](../stacks/s14-a2a-protocol.md)).

## Forces
- An agent acts on its own and at machine speed; a broad static key in its hands is a standing liability
- Human IAM assumes a person behind each login — agents cross trust boundaries and act for others
- Scoping tightly adds plumbing; scoping loosely means one hijack reaches everything
- The credential proves *who*, but a hijacked agent with valid creds is still a breach

## The move

- **Give every agent a first-class identity.** Unique, persistent, distinct from the human it acts for *and* from generic service accounts, with its own baseline permissions. Never share one credential across agents — that collapses attribution and widens blast radius.
- **Issue scoped, short-lived, just-in-time tokens.** Zero Standing Privilege: narrow to one resource/action, expire fast, minted at access time. A refund agent scoped to *one* customer ID for 60 seconds means a prompt injection maxes out at one refund, not a database dump.
- **Delegate, don't impersonate.** Use OAuth 2.0 Token Exchange (RFC 8693) with the `act` claim so the chain of who-authorized-whom travels with the call. OAuth 2.1 is required by the MCP spec ([S-10](../stacks/s10-mcp.md)) for remote-server auth.
- **Defend the token itself.** Bind it to a client cert (mTLS or DPoP) so a stolen bearer token is useless, and prefer cryptographic workload identity (SPIFFE/SPIRE, OIDC federation) over long-lived shared secrets.
- **Know the limits.** Recursive agent-to-agent delegation can't yet be cryptographically anchored back to a responsible human past a hop or two — and auth alone does nothing if the agent is hijacked. Pair identity with least privilege, human approval on sensitive actions ([F-09](f09-human-in-the-loop.md)), and behavioral monitoring.

## Receipt
> Technical anchors are named standards: OAuth 2.0 Token Exchange ([RFC 8693](https://datatracker.ietf.org/doc/html/rfc8693)) with the `act` claim; OAuth 2.1 required by the MCP spec; SPIFFE/SPIRE for workload identity; DPoP/mTLS for token binding; OWASP Top 10 for Agentic Applications (2026) and the EU AI Act (Aug 2026) as governing frameworks. The "machine identities outnumber humans ~45:1–100:1" and "only ~24% of orgs have full agent-to-agent visibility" figures are reported survey numbers (directional). The 60-second single-customer refund token is an illustrative pattern, not a measured run. Verified 2026-06-25; not independently implemented here.

## See also
[S-10](../stacks/s10-mcp.md) · [S-14](../stacks/s14-a2a-protocol.md) · [F-05](f05-agent-failure-taxonomy.md) · [F-09](f09-human-in-the-loop.md) · [F-06](f06-agent-sandboxing.md)

## Go deeper
Keywords: `non-human identity` · `OAuth 2.1` · `RFC 8693 token exchange` · `act claim` · `zero standing privilege` · `SPIFFE SPIRE` · `DPoP` · `mTLS` · `least privilege` · `OWASP agentic top 10`
