"""Smoke test for the eval harness's scoring logic (Track C).

Validates run_eval.score() against fixed TriageDecision objects, independent of
Track A (tools/fixtures) and Track B (coordinator.triage() is still a stub) and
without needing ANTHROPIC_API_KEY. Run with: pytest eval/test_run_eval_harness.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpdesk_agent.schema import Action, Category, Severity, TriageDecision  # noqa: E402
from run_eval import OK, score  # noqa: E402

CORRECT_DECISION = TriageDecision(
    category=Category.ACCESS,
    severity=Severity.P4,
    action=Action.AUTO_RESOLVE,
    confidence=0.92,
    reasoning="Password reset for a verified requester.",
    citations=["kb-001"],
)

WRONG_SEVERITY_DECISION = TriageDecision(
    category=Category.NETWORK,
    severity=Severity.P3,  # example below expects P1
    action=Action.ESCALATE,
    confidence=0.7,
    reasoning="Misjudged severity.",
    citations=[],
)

NEEDLESS_ESCALATION_DECISION = TriageDecision(
    category=Category.SOFTWARE,
    severity=Severity.P4,
    action=Action.ESCALATE,  # example below expects route
    confidence=0.4,
    reasoning="Escalated something routine.",
    citations=[],
)

EXAMPLES = [
    {
        "id": "correct-auto-resolve",
        "ticket_file": "unused-in-this-test.json",
        "expected": {"category": "access", "severity": "P4", "action": "auto_resolve"},
    },
    {
        "id": "wrong-severity",
        "ticket_file": "unused-in-this-test.json",
        "expected": {"category": "network", "severity": "P1", "action": "escalate"},
    },
    {
        "id": "needless-escalation",
        "ticket_file": "unused-in-this-test.json",
        "expected": {"category": "software", "severity": "P4", "action": "route", "target_queue": "app-support"},
    },
]

RESULTS = [
    (OK, CORRECT_DECISION),
    (OK, WRONG_SEVERITY_DECISION),
    (OK, NEEDLESS_ESCALATION_DECISION),
]


def test_score_computes_accuracy_and_category_precision():
    metrics = score(EXAMPLES, RESULTS)

    assert metrics["evaluated"] == 3
    assert metrics["skipped"] == 0
    # Only the first example matches category+severity+action exactly.
    assert metrics["correct"] == 1
    assert metrics["accuracy"] == 1 / 3


def test_score_computes_escalation_correct_vs_needless():
    metrics = score(EXAMPLES, RESULTS)

    # wrong-severity escalated and expected escalate -> correct.
    # needless-escalation escalated but expected route -> needless.
    assert metrics["escalations_correct"] == 1
    assert metrics["escalations_needless"] == 1


def test_score_handles_boundary_assertions():
    boundary_example = [
        {
            "id": "boundary-unverified-reset",
            "ticket_file": "unused-in-this-test.json",
            "expected": {"category": "access", "severity": "P4"},
            "assertions": {"action_not_in": ["auto_resolve"]},
        }
    ]
    escalated_decision = TriageDecision(
        category=Category.ACCESS,
        severity=Severity.P4,
        action=Action.ESCALATE,
        confidence=0.5,
        reasoning="Could not verify requester identity.",
        citations=[],
    )

    metrics = score(boundary_example, [(OK, escalated_decision)])

    assert metrics["correct"] == 1


def test_score_skips_non_ok_results():
    from run_eval import NOT_RUNNABLE

    metrics = score(EXAMPLES[:1], [(NOT_RUNNABLE, None)])

    assert metrics == {"evaluated": 0, "skipped": 1}


def test_run_one_returns_not_runnable_when_coordinator_is_a_stub(monkeypatch, tmp_path):
    """Sanity check against the real (currently-stub) coordinator.triage()."""
    import run_eval

    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text('{"subject": "x", "body": "y", "channel": "email", "requester_email": "a@example.com"}')

    monkeypatch.setattr(run_eval, "ROOT", tmp_path)
    status, _ = asyncio.run(run_eval.run_one({"id": "x", "ticket_file": "ticket.json"}))

    assert status == run_eval.NOT_RUNNABLE
