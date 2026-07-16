"""Decision schema — the shared contract (Track B owns this file).

This is what the coordinator must emit and the validation-retry loop checks
against. Keep this in sync with the decision table in ../../CLAUDE.md.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    ACCESS = "access"
    NETWORK = "network"
    HARDWARE = "hardware"
    SOFTWARE = "software"
    SECURITY = "security"


class Severity(str, Enum):
    P1 = "P1"  # business-down / many blocked / active security incident
    P2 = "P2"  # one user fully blocked or a team degraded, no workaround
    P3 = "P3"  # degraded but has a workaround
    P4 = "P4"  # low / cosmetic / request


class Action(str, Enum):
    AUTO_RESOLVE = "auto_resolve"
    ROUTE = "route"
    ESCALATE = "escalate"


# Category -> owning queue. TODO(Track B): confirm queue names with the team.
CATEGORY_QUEUE_MAP: dict[Category, str] = {
    Category.ACCESS: "identity-access",
    Category.NETWORK: "network-ops",
    Category.HARDWARE: "desktop-support",
    Category.SOFTWARE: "app-support",
    Category.SECURITY: "security-incident",
}


class TriageDecision(BaseModel):
    """The agent's decision. Validated before any action is taken."""

    category: Category
    severity: Severity
    action: Action
    target_queue: str | None = Field(
        default=None, description="Queue for a route action; null for auto_resolve/escalate."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Why this decision, in one short paragraph.")
    citations: list[str] = Field(
        default_factory=list, description="KB article ids / system-of-record refs used."
    )


# JSON Schema for the SDK's output_format.
DECISION_JSON_SCHEMA = TriageDecision.model_json_schema()
