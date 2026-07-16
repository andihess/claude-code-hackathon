# CLAUDE.md — IT Helpdesk Triage Agent (Scenario 5)

Shared conventions for this repo. Read [scenario-05-agentic-solution/GOAL.md](scenario-05-agentic-solution/GOAL.md)
for the full goal. This file is the **contract** three people build against in parallel —
change it deliberately and in small commits, because everyone depends on it.

## What we're building

A coordinator agent on the **Claude Agent SDK (Python)** that triages inbound IT helpdesk
requests. It makes a **real decision** — classify → enrich → decide → act → log — not chat.
Focus this pass: Challenge 3 (Tools) + Challenge 4 (Triage).

## Repo layout & ownership

Each track owns a directory. Stay in your lane to avoid conflicts; the only co-owned file
is this one.

```
scenario-05-agentic-solution/
  helpdesk_agent/
    tools/          # Track A — custom tools (@tool + create_sdk_mcp_server)
    coordinator.py  # Track B — agent loop
    schema.py       # Track B — decision schema (shared contract, edit carefully)
    validation.py   # Track B — validation-retry loop
    logging/        # Track B — reasoning-chain logs
  fixtures/
    systems/        # Track A — fake KB, requester dir, asset db
    tickets/        # Track C — sample inbound requests
  eval/             # Track C — eval runner + labeled expectations
README.md           # Track C — the pitch (judged)
presentation.html   # Track C — HTML deck (judged)
CLAUDE.md           # co-owned — this file (judged)
```

## The decision (shared contract)

The agent must emit **exactly this JSON**, validated before any action. Track B owns
`schema.py`; keep this table and that schema in sync.

```json
{
  "category": "access | network | hardware | software | security",
  "severity": "P1 | P2 | P3 | P4",
  "action": "auto_resolve | route | escalate",
  "target_queue": "string | null",
  "confidence": 0.0,
  "reasoning": "why this decision, in one short paragraph",
  "citations": ["kb-article-id or system-of-record ref, ..."]
}
```

## Severity — explicit thresholds (not vibes)

Use these definitions verbatim in prompts. "Urgent" in the body does **not** raise severity
by itself; impact and scope do.

| Sev | Definition | Examples |
|-----|------------|----------|
| **P1** | Business-down or many users blocked; security incident in progress | Site outage, active breach, exec fully unable to work before a board meeting |
| **P2** | One user fully blocked, or a team degraded, no workaround | Can't log in at all *with no quick fix* (account/identity broken, SSO down), shared drive down for a team |
| **P3** | Degraded but has a workaround | Slow VPN, one app flaky |
| **P4** | Low / cosmetic / request | "How do I…", cosmetic UI, non-urgent access request, **routine password reset** (immediate standard fix — a lockout is transient, so don't raise on urgency) |

## Action rules — explicit (category + confidence + impact)

- **auto_resolve** — only for `access` password resets **and** `confidence >= 0.85` **and**
  requester verified via `lookup_requester`. Nothing else auto-resolves this pass.
- **escalate** — `severity == P1`, OR `confidence < 0.60`, OR `category == security`.
  Escalation is the safe default when unsure — prefer it over a low-confidence route.
- **route** — everything else, to the queue from the category→queue map (in `schema.py`).

## Tool design rules (Track A)

- ~4–5 tools total. Reliability drops past that.
- Each tool description says **what it does AND what it does not do**, input formats, and an
  example query. Teach the agent *when* to reach for it.
- Errors return a **structured** response, never a raw string:
  ```python
  return {
      "content": [{"type": "text", "text": "Requester not found for email X"}],
      "is_error": True,
      # include a reason code + guidance in the text so the agent can recover
  }
  ```
- Reads (`kb_lookup`, `lookup_requester`, `lookup_asset`, `check_queue_load`) are pure and
  side-effect free. Only `route_ticket` writes.
- Tools are exposed via `create_sdk_mcp_server(name="helpdesk", ...)`; the agent references
  them as `mcp__helpdesk__<tool_name>`.

## Coordinator rules (Track B)

- Loop: ingest → classify → enrich (kb + system-of-record) → decide → act → log.
- Structured output via `output_format` (JSON Schema from `schema.py`).
- **Validation-retry loop:** validate the decision; on failure feed the *specific* error
  back and retry up to **3** times. Log `retry_count` and `error_type` per request.
- **Log the reasoning chain, not just the answer** — every decision must be replayable from
  the log alone (input, tool calls + results, retries, final decision).

## Python conventions

- Python 3.11+, `async`/`await` throughout (SDK is async).
- Tool handlers: `async def handler(args: dict[str, Any]) -> dict[str, Any]`.
- Type hints on all public functions. Prefer `pydantic` models for the decision + schema.
- Model alias `"sonnet"` by default; keep model choice in one config spot, not scattered.
- Never hardcode secrets. `ANTHROPIC_API_KEY` comes from the environment.
- No real/internal data anywhere — fixtures are synthetic and safe to share.

## Git workflow — trunk-based

- **Commit small and often, straight to `main`.** No long-lived branches.
- Keep each commit to your own directory where possible; if you must touch `CLAUDE.md` or
  `schema.py`, make it a tiny, isolated commit and call it out to the team.
- `git pull --rebase` before pushing to keep history linear.
- Commit messages: imperative, scoped — e.g. `tools: add kb_lookup with structured errors`.
- Commit history is part of the submission — make it tell the story.

## How to run

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate   |   Windows: .venv\Scripts\Activate.ps1
pip install claude-agent-sdk pydantic
$env:ANTHROPIC_API_KEY="..."   # PowerShell   (bash: export ANTHROPIC_API_KEY=...)
python -m helpdesk_agent.triage --input fixtures/tickets/sample.json
```

## Out of scope this pass (leave clean seams)

Ch.5 The Brake (permission hooks), Ch.6 The Attack (adversarial evals), Ch.7 The Scorecard
(CI eval). Design tool/coordinator interfaces so these drop in later without rework.
