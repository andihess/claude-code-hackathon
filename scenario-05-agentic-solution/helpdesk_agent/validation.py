"""Validation-retry loop (Track B).

Validates the agent's raw output against the decision schema. On failure, returns
a specific, human-readable error to feed back to Claude for the next attempt.
Log retry_count and error_type per request.

See ../../CLAUDE.md ("Coordinator rules").
"""

from __future__ import annotations

MAX_RETRIES = 3


# TODO(Track B): implement.
# - validate_decision(raw) -> (TriageDecision | None, error_message | None)
# - build the feedback string fed back on retry (be specific about the failing field)
