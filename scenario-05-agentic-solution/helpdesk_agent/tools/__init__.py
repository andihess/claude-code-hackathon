"""Custom tools (Track A).

Exposed to the agent via create_sdk_mcp_server(name="helpdesk", ...); the agent
references them as mcp__helpdesk__<tool_name>.

Tools (~5). Reads are pure/side-effect-free (readOnlyHint=True); only route_ticket
writes:
  - kb_lookup         (knowledge lookup)
  - lookup_requester  (system-of-record read)
  - lookup_asset      (system-of-record read)
  - check_queue_load  (read helper for routing)
  - route_ticket      (the write action)

Each tool's description teaches WHEN to use it and what it does NOT do, with input
formats and an example query. Errors return a structured response
(is_error=True + a reason code + guidance), never a raw string.

See ../../CLAUDE.md ("Tool design rules").
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

# --------------------------------------------------------------------------- #
# Fixture access                                                              #
# --------------------------------------------------------------------------- #

# .../helpdesk_agent/tools/__init__.py -> parents[2] == scenario-05-agentic-solution
_SCENARIO_ROOT = Path(__file__).resolve().parents[2]


def _fixtures_dir() -> Path:
    """Directory holding the synthetic systems-of-record.

    Overridable with HELPDESK_FIXTURES_DIR (useful for tests / alt datasets).
    """
    override = os.environ.get("HELPDESK_FIXTURES_DIR")
    return Path(override) if override else _SCENARIO_ROOT / "fixtures" / "systems"


def _route_log_path() -> Path:
    """Where route_ticket appends its write record (the only side effect).

    Overridable with HELPDESK_ROUTE_LOG.
    """
    override = os.environ.get("HELPDESK_ROUTE_LOG")
    return Path(override) if override else _SCENARIO_ROOT / "routed_tickets.jsonl"


@lru_cache(maxsize=None)
def _load_json(relpath: str) -> Any:
    """Load and cache a JSON fixture relative to the fixtures dir."""
    path = _fixtures_dir() / relpath
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Structured response helpers                                                 #
# --------------------------------------------------------------------------- #


def _ok(payload: Any) -> dict[str, Any]:
    """Success response. Payload is JSON-encoded into a single text block so the
    agent gets machine-readable data it can cite."""
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def _err(reason_code: str, message: str, guidance: str) -> dict[str, Any]:
    """Structured error. Bundles a stable reason code + recovery guidance so the
    agent can recover (retry differently, fall back, or escalate) rather than
    seeing an opaque string."""
    body = {
        "error": True,
        "reason_code": reason_code,
        "message": message,
        "guidance": guidance,
    }
    return {"content": [{"type": "text", "text": json.dumps(body, indent=2)}], "is_error": True}


_READ_ONLY = ToolAnnotations(readOnlyHint=True)


# --------------------------------------------------------------------------- #
# Tools                                                                       #
# --------------------------------------------------------------------------- #


@tool(
    "kb_lookup",
    (
        "Search the IT knowledge base for the runbook that best matches a helpdesk "
        "request, to ground the category/severity/action decision in a cited article.\n\n"
        "USE THIS to find resolution steps, auto-resolution eligibility, and severity "
        "guidance for an issue (password reset, VPN, phishing, etc.).\n"
        "DOES NOT: resolve or route anything, read requester/asset records, or invent "
        "articles — it only returns articles that exist in the KB. If nothing matches, it "
        "says so; do not fabricate a KB id.\n\n"
        "Input: {\"query\": str (required, free-text from the ticket subject/body), "
        "\"category\": one of access|network|hardware|software|security (optional filter)}.\n"
        "Returns: ranked matching articles with id, title, category, summary, and body.\n"
        "Example query: {\"query\": \"can't sign in, forgot my password\", \"category\": \"access\"}."
    ),
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text issue description from the ticket."},
            "category": {
                "type": "string",
                "enum": ["access", "network", "hardware", "software", "security"],
                "description": "Optional category filter.",
            },
        },
        "required": ["query"],
    },
    annotations=_READ_ONLY,
)
async def kb_lookup(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip().lower()
    if not query:
        return _err(
            "empty_query",
            "kb_lookup called with an empty query.",
            "Pass the ticket subject/body text as 'query'.",
        )
    category = (args.get("category") or "").strip().lower() or None

    try:
        index = _load_json("kb/index.json")
    except (OSError, json.JSONDecodeError) as exc:
        return _err("kb_unavailable", f"Could not read KB index: {exc}", "Escalate; KB is unavailable.")

    scored: list[tuple[int, dict[str, Any]]] = []
    for article in index.get("articles", []):
        if category and article.get("category") != category:
            continue
        score = 0
        for kw in article.get("keywords", []):
            if kw.lower() in query:
                score += 2
        for word in article.get("title", "").lower().split():
            if len(word) > 3 and word in query:
                score += 1
        if score:
            scored.append((score, article))

    if not scored:
        return _err(
            "no_match",
            f"No KB article matched query={args.get('query')!r} category={category!r}.",
            "Decide from the request text and thresholds in the prompt; cite no KB id, or "
            "retry kb_lookup without the category filter.",
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, article in scored[:3]:
        body = None
        try:
            body_path = _fixtures_dir() / "kb" / f"{article['id']}.md"
            if body_path.exists():
                body = body_path.read_text(encoding="utf-8")
        except OSError:
            body = None
        results.append(
            {
                "id": article["id"],
                "title": article["title"],
                "category": article["category"],
                "summary": article.get("summary"),
                "match_score": score,
                "body": body,
            }
        )
    return _ok({"matches": results})


@tool(
    "lookup_requester",
    (
        "Look up the person who filed a ticket in the requester directory, to verify "
        "identity and pull org context (VIP status, department, account status, MFA).\n\n"
        "USE THIS whenever a decision depends on who the requester is — required before "
        "auto-resolving an access request, and useful for judging impact/severity.\n"
        "DOES NOT: change accounts, reset passwords, or route tickets; it is read-only. It "
        "does not look up devices (use lookup_asset) or KB articles (use kb_lookup).\n\n"
        "Input: {\"email\": str (required, the requester's email; case-insensitive)}.\n"
        "Returns: the requester profile (name, department, org_unit, vip, account_status, "
        "identity_verified, mfa_enrolled, assigned_assets).\n"
        "Example query: {\"email\": \"dana.okafor@acme-synthetic.example\"}."
    ),
    {"email": str},
    annotations=_READ_ONLY,
)
async def lookup_requester(args: dict[str, Any]) -> dict[str, Any]:
    email = (args.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err(
            "invalid_email",
            f"'{args.get('email')}' is not a valid email.",
            "Provide the requester's email address as 'email'.",
        )
    try:
        directory = _load_json("requesters.json")
    except (OSError, json.JSONDecodeError) as exc:
        return _err("directory_unavailable", f"Could not read requester directory: {exc}", "Escalate; identity cannot be verified.")

    record = directory.get("requesters", {}).get(email)
    if record is None:
        return _err(
            "requester_not_found",
            f"No requester found for email {email!r}.",
            "Identity is unverified — do NOT auto-resolve. Treat as unverified and route or "
            "escalate per the rules.",
        )
    return _ok(record)


@tool(
    "lookup_asset",
    (
        "Look up a device/asset record by its asset tag, to confirm ownership, status, "
        "OS, encryption, and warranty when a ticket concerns specific hardware.\n\n"
        "USE THIS for hardware/software tickets that reference a device (e.g. 'my laptop "
        "LT-4471 won't boot') to enrich the decision.\n"
        "DOES NOT: look people up by email (use lookup_requester), search the KB, or modify "
        "asset records; it is read-only. It only accepts an asset TAG, not an email or name.\n\n"
        "Input: {\"asset_tag\": str (required, e.g. 'LT-4471'; case-insensitive)}.\n"
        "Returns: the asset record (type, model, os, assigned_to, status, encrypted, warranty).\n"
        "Example query: {\"asset_tag\": \"LT-4471\"}."
    ),
    {"asset_tag": str},
    annotations=_READ_ONLY,
)
async def lookup_asset(args: dict[str, Any]) -> dict[str, Any]:
    tag = (args.get("asset_tag") or "").strip().upper()
    if not tag:
        return _err(
            "invalid_asset_tag",
            "lookup_asset called without an asset_tag.",
            "Provide the device asset tag (e.g. 'LT-4471'). If the ticket has no tag, skip "
            "this tool and decide from the description.",
        )
    try:
        assets = _load_json("assets.json")
    except (OSError, json.JSONDecodeError) as exc:
        return _err("asset_db_unavailable", f"Could not read asset database: {exc}", "Proceed without asset context.")

    record = assets.get("assets", {}).get(tag)
    if record is None:
        return _err(
            "asset_not_found",
            f"No asset found for tag {tag!r}.",
            "The tag may be mistyped or not in inventory. Decide from the description; do not "
            "invent asset details.",
        )
    return _ok(record)


@tool(
    "check_queue_load",
    (
        "Read current load for support queues (open tickets, agents available, avg wait), "
        "to inform routing — e.g. to note a queue is backlogged.\n\n"
        "USE THIS after you know the category/target queue, to sanity-check routing.\n"
        "DOES NOT: route or assign tickets (use route_ticket), and does NOT change the target "
        "queue — the queue is fixed by category. It is read-only and advisory only.\n\n"
        "Input: {\"queue\": str (optional; one of identity-access|network-ops|desktop-support|"
        "app-support|security-incident). Omit to get all queues}.\n"
        "Returns: load snapshot(s) with open_tickets, agents_available, avg_wait_minutes, status.\n"
        "Example query: {\"queue\": \"network-ops\"}."
    ),
    {
        "type": "object",
        "properties": {
            "queue": {
                "type": "string",
                "enum": [
                    "identity-access",
                    "network-ops",
                    "desktop-support",
                    "app-support",
                    "security-incident",
                ],
                "description": "Optional queue name; omit for all queues.",
            }
        },
        "required": [],
    },
    annotations=_READ_ONLY,
)
async def check_queue_load(args: dict[str, Any]) -> dict[str, Any]:
    try:
        data = _load_json("queues.json")
    except (OSError, json.JSONDecodeError) as exc:
        return _err("queues_unavailable", f"Could not read queue data: {exc}", "Route anyway; load is advisory only.")

    queues = data.get("queues", {})
    requested = (args.get("queue") or "").strip().lower() or None
    if requested is None:
        return _ok({"queues": list(queues.values())})

    record = queues.get(requested)
    if record is None:
        return _err(
            "queue_not_found",
            f"No queue named {requested!r}.",
            f"Valid queues: {', '.join(sorted(queues))}.",
        )
    return _ok(record)


@tool(
    "route_ticket",
    (
        "Commit the triage outcome: assign the ticket to a queue (or mark it for escalation/"
        "auto-resolution) and write an auditable routing record. This is the ONLY tool with a "
        "side effect — call it exactly once, last, after the decision is finalized.\n\n"
        "USE THIS to enact a decision you have already made and validated.\n"
        "DOES NOT: make the decision for you, look anything up, or validate the schema — do the "
        "classification and enrichment first. Do not call it more than once per ticket.\n\n"
        "Input: {\"target_queue\": str|null (required; null only when action is escalate/"
        "auto_resolve), \"category\": access|network|hardware|software|security (required), "
        "\"severity\": P1|P2|P3|P4 (required), \"action\": auto_resolve|route|escalate (required), "
        "\"requester_email\": str (required), \"summary\": str (required, one line)}.\n"
        "Returns: {routing_id, status:'recorded', ...} on success.\n"
        "Example query: {\"target_queue\": \"network-ops\", \"category\": \"network\", "
        "\"severity\": \"P3\", \"action\": \"route\", "
        "\"requester_email\": \"lin.wei@acme-synthetic.example\", \"summary\": \"VPN slow\"}."
    ),
    {
        "type": "object",
        "properties": {
            "target_queue": {
                "type": ["string", "null"],
                "description": "Queue for a route action; null for escalate/auto_resolve.",
            },
            "category": {
                "type": "string",
                "enum": ["access", "network", "hardware", "software", "security"],
            },
            "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "action": {"type": "string", "enum": ["auto_resolve", "route", "escalate"]},
            "requester_email": {"type": "string"},
            "summary": {"type": "string", "description": "One-line summary of the ticket."},
        },
        "required": ["category", "severity", "action", "requester_email", "summary"],
    },
)
async def route_ticket(args: dict[str, Any]) -> dict[str, Any]:
    action = (args.get("action") or "").strip()
    target_queue = args.get("target_queue")

    if action == "route" and not target_queue:
        return _err(
            "missing_target_queue",
            "action='route' requires a non-null target_queue.",
            "Provide the queue from the category→queue map, or use action 'escalate'.",
        )
    if action in ("escalate", "auto_resolve") and target_queue:
        return _err(
            "unexpected_target_queue",
            f"action={action!r} must have target_queue=null (got {target_queue!r}).",
            "Set target_queue to null for escalate/auto_resolve.",
        )
    for field in ("category", "severity", "requester_email", "summary"):
        if not (args.get(field) or "").strip():
            return _err("missing_field", f"route_ticket missing required field {field!r}.", f"Provide {field!r}.")

    routing_id = f"RT-{uuid.uuid4().hex[:8].upper()}"
    record = {
        "routing_id": routing_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "target_queue": target_queue,
        "category": args["category"],
        "severity": args["severity"],
        "requester_email": args["requester_email"],
        "summary": args["summary"],
    }
    try:
        path = _route_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        return _err("write_failed", f"Could not persist routing record: {exc}", "Retry; if it persists, escalate manually.")

    return _ok({"status": "recorded", **record})


# --------------------------------------------------------------------------- #
# MCP server                                                                  #
# --------------------------------------------------------------------------- #

HELPDESK_TOOLS = [kb_lookup, lookup_requester, lookup_asset, check_queue_load, route_ticket]

helpdesk_server = create_sdk_mcp_server(name="helpdesk", version="1.0.0", tools=HELPDESK_TOOLS)

# Fully-qualified names the agent uses / that Track B allow-lists.
TOOL_NAMES = [
    "mcp__helpdesk__kb_lookup",
    "mcp__helpdesk__lookup_requester",
    "mcp__helpdesk__lookup_asset",
    "mcp__helpdesk__check_queue_load",
    "mcp__helpdesk__route_ticket",
]

__all__ = ["helpdesk_server", "HELPDESK_TOOLS", "TOOL_NAMES"]
