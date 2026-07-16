"""Validation-retry loop (Track B).

Validates the agent's raw output against the decision schema. On failure, returns
a specific, human-readable error to feed back to Claude for the next attempt.
Log retry_count and error_type per request.

See ../../CLAUDE.md ("Coordinator rules" and "Action rules").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .schema import CATEGORY_QUEUE_MAP, Action, Category, Severity, TriageDecision

MAX_RETRIES = 3

LOOKUP_REQUESTER_TOOL = "mcp__helpdesk__lookup_requester"


@dataclass
class ValidationFailure:
    """A specific, retryable validation error."""

    error_type: str
    message: str


def validate_decision(
    raw: dict[str, Any],
    tool_names_called: set[str] | None = None,
) -> tuple[TriageDecision | None, ValidationFailure | None]:
    """Validate raw model output: schema first, then the action rules.

    Args:
        raw: The candidate decision as returned by output_format.
        tool_names_called: Names of tools invoked earlier in this turn (e.g.
            {"mcp__helpdesk__lookup_requester"}), used to check the
            "requester verified" precondition for auto_resolve.

    Returns:
        (decision, None) on success, or (None, failure) with a message meant
        to be fed back to Claude verbatim on retry.
    """
    try:
        decision = TriageDecision.model_validate(raw)
    except ValidationError as exc:
        return None, ValidationFailure("schema", _format_schema_error(exc))

    failure = _check_action_rules(decision, tool_names_called or set())
    if failure is not None:
        return None, failure

    return decision, None


def build_retry_feedback(failure: ValidationFailure) -> str:
    """Turn a ValidationFailure into the next user turn sent back to Claude."""
    return (
        "Your previous decision was invalid and was rejected before any action was "
        f"taken. {failure.message} Re-emit the complete, corrected decision JSON."
    )


def _format_schema_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        field = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"`{field}`: {err['msg']} (got {err.get('input')!r})")
    return "The decision failed schema validation:\n" + "\n".join(lines)


def _check_action_rules(
    decision: TriageDecision, tool_names_called: set[str]
) -> ValidationFailure | None:
    """CLAUDE.md 'Action rules' — checked here because they mix fields
    (severity/confidence/category) with evidence (tool calls) that the JSON
    schema alone cannot express.
    """
    must_escalate_reasons = []
    if decision.severity == Severity.P1:
        must_escalate_reasons.append("severity is P1")
    if decision.confidence < 0.60:
        must_escalate_reasons.append(f"confidence {decision.confidence} < 0.60")
    if decision.category == Category.SECURITY:
        must_escalate_reasons.append("category is security")

    if must_escalate_reasons and decision.action != Action.ESCALATE:
        reasons = " and ".join(must_escalate_reasons)
        return ValidationFailure(
            "rule:escalate_required",
            f"action must be 'escalate' because {reasons}, but got "
            f"action={decision.action.value!r}.",
        )

    if decision.action == Action.AUTO_RESOLVE:
        if decision.category != Category.ACCESS:
            return ValidationFailure(
                "rule:auto_resolve_category",
                "auto_resolve is only allowed for category=access, got "
                f"category={decision.category.value!r}.",
            )
        if decision.confidence < 0.85:
            return ValidationFailure(
                "rule:auto_resolve_confidence",
                f"auto_resolve requires confidence >= 0.85, got {decision.confidence}.",
            )
        if LOOKUP_REQUESTER_TOOL not in tool_names_called:
            return ValidationFailure(
                "rule:auto_resolve_unverified",
                "auto_resolve requires the requester to be verified via "
                f"{LOOKUP_REQUESTER_TOOL} first; no such tool call was seen.",
            )
        if decision.target_queue is not None:
            return ValidationFailure(
                "rule:auto_resolve_target_queue",
                "auto_resolve must have target_queue=null.",
            )
        return None

    if decision.action == Action.ESCALATE:
        if decision.target_queue is not None:
            return ValidationFailure(
                "rule:escalate_target_queue",
                "escalate must have target_queue=null.",
            )
        return None

    # action == route
    expected_queue = CATEGORY_QUEUE_MAP[decision.category]
    if decision.target_queue != expected_queue:
        return ValidationFailure(
            "rule:route_target_queue",
            f"route for category={decision.category.value!r} must set "
            f"target_queue={expected_queue!r}, got {decision.target_queue!r}.",
        )
    return None
