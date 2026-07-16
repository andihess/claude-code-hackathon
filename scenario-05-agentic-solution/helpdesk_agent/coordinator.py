"""Coordinator agent (Track B).

Loop: ingest -> classify -> enrich (kb + system-of-record) -> decide -> act -> log.
Uses the Claude Agent SDK's ClaudeSDKClient with output_format bound to
DECISION_JSON_SCHEMA, wrapped in the validation-retry loop (validation.py).

See ../../CLAUDE.md ("Coordinator rules") for the contract.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from .logging import ReasoningChain, write_log
from .schema import DECISION_JSON_SCHEMA, Action, Category, Severity, TriageDecision
from .validation import MAX_RETRIES, ValidationFailure, build_retry_feedback, validate_decision

# Single config spot for model choice, per CLAUDE.md's Python conventions.
MODEL = "sonnet"

HELPDESK_TOOLS = [
    "mcp__helpdesk__kb_lookup",
    "mcp__helpdesk__lookup_requester",
    "mcp__helpdesk__lookup_asset",
    "mcp__helpdesk__check_queue_load",
    "mcp__helpdesk__route_ticket",
]

MAX_TURNS = 20

SYSTEM_PROMPT = """\
You are the IT helpdesk triage coordinator. You do not chat with the requester; you \
make a triage decision that a downstream system acts on.

Work the loop: classify -> enrich -> decide -> act.
- Classify: form an initial view of category and severity from the subject/body.
- Enrich: use the helpdesk tools before deciding. Look up the requester
  (mcp__helpdesk__lookup_requester), search the knowledge base for a known
  resolution (mcp__helpdesk__kb_lookup), check the relevant asset if one is
  named (mcp__helpdesk__lookup_asset), and check queue load if it's close
  between routing options (mcp__helpdesk__check_queue_load).
- Decide: pick category, severity, action, target_queue, confidence, and cite
  the KB articles / system-of-record lookups that justify the decision.
- Act: call mcp__helpdesk__route_ticket to record the action before you finish.

Severity is judged by impact and scope, never by tone. The word "urgent" in a
request body does NOT raise severity by itself.
- P1: business-down, or many users blocked, or an active security incident.
- P2: one user fully blocked, or a team degraded, with no workaround.
- P3: degraded but a workaround exists.
- P4: low priority, cosmetic, or a how-do-I request.

Action rules, applied in this order:
- escalate: severity is P1, OR confidence < 0.60, OR category is security.
  When unsure, escalate rather than guessing a route with low confidence.
- auto_resolve: ONLY for category=access password resets, AND confidence >= 0.85,
  AND you have verified the requester via mcp__helpdesk__lookup_requester.
  Nothing else auto-resolves.
- route: everything else, to the queue that owns the category.

target_queue must be null for auto_resolve and escalate, and must be the owning
queue's name for route. Always include citations (KB article ids or
system-of-record references) that back up your decision.
"""


def _build_prompt(request: dict[str, Any]) -> str:
    return (
        "Triage this inbound IT support request and produce the decision JSON.\n\n"
        f"Channel: {request.get('channel')}\n"
        f"Requester: {request.get('requester_email')}\n"
        f"Subject: {request.get('subject')}\n"
        f"Body:\n{request.get('body')}\n"
    )


def _helpdesk_mcp_server() -> Any:
    """Track A owns tools/__init__.py and its create_sdk_mcp_server(...) config.

    Imported lazily (not at module load) so this module stays importable -
    and schema/validation/logging stay testable - even before Track A's
    tools land, per CLAUDE.md's tool-exposure convention
    (mcp__helpdesk__<tool_name>).
    """
    from .tools import helpdesk_mcp_server  # noqa: PLC0415

    return helpdesk_mcp_server


def _fallback_escalate(errors: list[ValidationFailure], last_raw: dict[str, Any]) -> TriageDecision:
    """Retries exhausted: escalate is the safe default when unsure (CLAUDE.md).

    Salvage whatever fields were structurally plausible from the last attempt
    so a human reviewer isn't starting from nothing; force the fields that
    made every attempt fail (action/target_queue/confidence) to safe values.
    """
    try:
        category = Category(last_raw.get("category"))
    except ValueError:
        category = Category.SECURITY
    try:
        severity = Severity(last_raw.get("severity"))
    except ValueError:
        severity = Severity.P2

    error_summary = "; ".join(f"{e.error_type}: {e.message}" for e in errors)
    return TriageDecision(
        category=category,
        severity=severity,
        action=Action.ESCALATE,
        target_queue=None,
        confidence=0.0,
        reasoning=(
            f"Automatic escalation: no valid decision after {MAX_RETRIES} retries. "
            f"Routed to a human for manual triage. Last error(s): {error_summary}"
        ),
        citations=[],
    )


async def triage(request: dict[str, Any]) -> TriageDecision:
    """Triage one inbound request and return a validated TriageDecision.

    Args:
        request: {subject, body, channel, requester_email}
    """
    chain = ReasoningChain(request=request)
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"helpdesk": _helpdesk_mcp_server()},
        allowed_tools=HELPDESK_TOOLS,
        output_format=DECISION_JSON_SCHEMA,
        max_turns=MAX_TURNS,
    )

    tool_names_called: set[str] = set()
    pending_tool_calls: dict[str, tuple[str, dict[str, Any]]] = {}
    errors: list[ValidationFailure] = []
    last_raw: dict[str, Any] = {}
    decision: TriageDecision | None = None
    retry_count = 0

    async with ClaudeSDKClient(options=options) as client:
        await client.query(_build_prompt(request))

        while decision is None:
            structured_output: dict[str, Any] | None = None

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_names_called.add(block.name)
                            pending_tool_calls[block.id] = (block.name, block.input)
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            name, args = pending_tool_calls.pop(
                                block.tool_use_id, ("<unknown>", {})
                            )
                            chain.record_tool_call(
                                name, args, block.content, is_error=bool(block.is_error)
                            )
                elif isinstance(message, ResultMessage):
                    structured_output = message.structured_output

            last_raw = structured_output or {}
            decision, failure = validate_decision(last_raw, tool_names_called=tool_names_called)
            if decision is not None:
                break

            retry_count += 1
            errors.append(failure)
            chain.record_attempt_failure(retry_count, failure.error_type, failure.message)

            if retry_count >= MAX_RETRIES:
                decision = _fallback_escalate(errors, last_raw)
                break

            await client.query(build_retry_feedback(failure))

    write_log(chain.to_record(decision.model_dump(mode="json"), retry_count))
    return decision
