"""Reasoning-chain logging (Track B).

Every decision must be replayable from the log alone: input, tool calls + results,
retries (count + error type), and the final decision. One structured JSON record
per request (JSON Lines), so the Ch.7 eval harness can consume it without needing
the coordinator process.

See ../../CLAUDE.md ("Coordinator rules").
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "triage.jsonl"


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    result: Any
    is_error: bool = False


@dataclass
class AttemptRecord:
    attempt: int
    error_type: str
    message: str


@dataclass
class ReasoningChain:
    """Accumulates one request's trace as the coordinator works through it.

    Usage:
        chain = ReasoningChain(request=request)
        chain.record_tool_call(name, args, result)
        chain.record_attempt_failure(attempt=1, error_type=..., message=...)
        write_log(chain.to_record(final_decision, retry_count))
    """

    request: dict[str, Any]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    attempts: list[AttemptRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    def record_tool_call(
        self, name: str, args: dict[str, Any], result: Any, is_error: bool = False
    ) -> None:
        self.tool_calls.append(
            ToolCallRecord(name=name, args=args, result=result, is_error=is_error)
        )

    def record_attempt_failure(self, attempt: int, error_type: str, message: str) -> None:
        self.attempts.append(AttemptRecord(attempt=attempt, error_type=error_type, message=message))

    def to_record(
        self, final_decision: dict[str, Any] | None, retry_count: int
    ) -> dict[str, Any]:
        return {
            "timestamp": time.time(),
            "request": self.request,
            "tool_calls": [tc.__dict__ for tc in self.tool_calls],
            "attempts": [a.__dict__ for a in self.attempts],
            "retry_count": retry_count,
            "final_decision": final_decision,
            "duration_ms": round((time.monotonic() - self.started_at) * 1000, 1),
        }


def write_log(record: dict[str, Any], log_path: Path | str = DEFAULT_LOG_PATH) -> None:
    """Append one JSON record (one line) to the reasoning-chain log."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
