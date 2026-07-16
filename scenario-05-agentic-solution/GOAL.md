# Scenario 5 — Agentic Solution: IT Helpdesk Triage Agent

> **Goal doc for collaborators.** Read this first. It explains what we're building, why,
> what's in scope for this pass, and how we intend to divide the work.

## The Problem

Inbound IT support requests arrive through multiple channels (tickets, chat, "urgent"
emails to the CIO) and get hand-triaged by a human. Time-to-first-response is measured in
hours nobody is proud of. We're building an **agent that makes a real decision** — it
classifies, routes, and acts — not a chatbot.

## What the Agent Decides

Given an inbound request, the agent produces a **decision**, not a conversation:

- **Category** — e.g. account/access, network, hardware, software, security.
- **Severity** — **P1–P4** (P1 = business-down, P4 = low/cosmetic).
- **Action** — one of:
  - **auto-resolve** the trivial cases (e.g. password resets),
  - **route** to the owning team's queue, or
  - **escalate** to a human when confidence/impact warrants it.
- **Reasoning** — the full chain is logged so every decision is replayable from the log alone.

## Scope (this pass)

We are prioritizing **depth over breadth**. Focus:

| # | Challenge | In this pass? |
|---|-----------|---------------|
| 3 | **The Tools** — custom tools with structured errors | ✅ Yes |
| 4 | **The Triage** — coordinator agent + validation-retry loop | ✅ Yes |
| 1–2 | Mandate / Bones (one-pager + ADR) | Light — captured here |
| 5 | The Brake (human-in-the-loop hooks) | ⏭️ Follow-up |
| 6 | The Attack (adversarial eval set) | ⏭️ Follow-up |
| 7 | The Scorecard (CI eval harness) | ⏭️ Follow-up |

We will leave clean seams so the follow-up challenges drop in without rework.

## Planned Architecture

Coordinator agent loop:

```
Ingest → Classify → Enrich → Decide → Act → Log
```

1. **Ingest** — raw request (subject, body, channel, requester).
2. **Classify** — category + severity (P1–P4) + confidence.
3. **Enrich** — knowledge-base lookup + system-of-record read.
4. **Decide** — auto-resolve | route-to-queue | escalate.
5. **Act** — write tool creates/routes/auto-resolves the ticket.
6. **Log** — the full reasoning chain, replayable from the log alone.

The structured decision is wrapped in a **validation-retry loop** against a JSON schema:
on validation failure the specific error is fed back to Claude and it retries up to N
times. We log retry count and error type per request.

## Planned Tools (~4–5)

Each tool's description teaches **when to use it and what it does *not* do**, with input
formats and example queries. Errors return structured responses (`is_error: true` + reason
code + guidance) so the agent can recover gracefully rather than parse a string.

| Tool | Type | Purpose |
|------|------|---------|
| `kb_lookup` | knowledge lookup | Search the KB / runbooks for a resolution. |
| `lookup_requester` | system-of-record read | Requester profile, VIP status, org unit. |
| `lookup_asset` | system-of-record read | Device/asset status tied to the request. |
| `check_queue_load` | read helper | Current load per team queue, for routing. |
| `route_ticket` | **write action** | Create/route/auto-resolve the ticket. |

## Tech Stack

**Claude Agent SDK (Python)** — the required harness for this scenario.

- Custom tools via the `@tool` decorator, exposed through `create_sdk_mcp_server`.
- Agent loop via `query()` (one-off) / `ClaudeSDKClient` (multi-turn).
- Schema-validated structured output via `output_format` (JSON Schema); we retry on
  validation failure.
- Auth: `ANTHROPIC_API_KEY` in the environment.

## How We'll Divide the Work

Play every role regardless of day job:

- **PM/BA** — sharpen the Mandate (what it decides alone vs. escalates) in this doc.
- **Architect** — the coordinator/loop design + tool contracts.
- **Dev** — implement the tools and the coordinator + validation-retry loop.
- **Quality** — fixtures across categories (incl. a password reset and a P1) and a first
  eval pass.

## How to Run It

_To be filled in as we build. Expected shape:_

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install claude-agent-sdk
export ANTHROPIC_API_KEY=...                          # PowerShell: $env:ANTHROPIC_API_KEY="..."
python -m helpdesk_agent.triage --input fixtures/sample_ticket.json
```

## Status

- [x] Goal documented (this file)
- [ ] Custom tools implemented
- [ ] Coordinator + validation-retry loop
- [ ] Fixtures + end-to-end run
