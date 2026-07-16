"""Eval runner (Track C).

Runs helpdesk_agent.coordinator.triage() over eval/dataset.jsonl and scores the
decisions against labeled expectations in dataset.jsonl.

Metrics: overall accuracy, per-category precision, and escalation rate (correct
vs. needless). Adversarial set + false-confidence rate are follow-ups (Ch.6/7).

Usage (from anywhere):
    python scenario-05-agentic-solution/eval/run_eval.py

While helpdesk_agent.coordinator.triage() is still a stub (Track B not landed
yet), this prints how many fixtures loaded and validated cleanly, then exits
with status 2 rather than crashing on NotImplementedError.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from helpdesk_agent.coordinator import triage  # noqa: E402
from helpdesk_agent.schema import Action, Category, Severity  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "dataset.jsonl"

NOT_RUNNABLE = "not_runnable"
ERROR = "error"
OK = "ok"

# Severity is graded with a one-level tolerance in the SAFE direction only:
# a decision that is exact or up to one level MORE urgent than the label passes,
# but an under-severe call (less urgent than expected) still fails. This credits
# conservative triage while catching genuine under-prioritization and 2+ level
# over-escalation (e.g. rating a routine password reset P2).
_SEV_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _severity_ok(decision_severity: str, expected_severity: str) -> bool:
    gap = _SEV_RANK[expected_severity] - _SEV_RANK[decision_severity]
    return 0 <= gap <= 1


def load_dataset(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    examples = []
    with path.open() as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            example = json.loads(line)
            expected = example.get("expected", {})
            if "category" in expected and expected["category"] not in Category._value2member_map_:
                raise ValueError(f"{path}:{lineno} - invalid category {expected['category']!r}")
            if "severity" in expected and expected["severity"] not in Severity._value2member_map_:
                raise ValueError(f"{path}:{lineno} - invalid severity {expected['severity']!r}")
            if "action" in expected and expected["action"] not in Action._value2member_map_:
                raise ValueError(f"{path}:{lineno} - invalid action {expected['action']!r}")
            examples.append(example)
    return examples


async def run_one(example: dict[str, Any]) -> tuple[str, Any]:
    ticket_path = ROOT / example["ticket_file"]
    ticket = json.loads(ticket_path.read_text())
    try:
        decision = await triage(ticket)
    except NotImplementedError:
        return NOT_RUNNABLE, None
    except Exception as exc:  # noqa: BLE001 - eval harness must never crash on one bad case
        return ERROR, str(exc)
    return OK, decision


def _action_matches(decision_action: str, example: dict[str, Any]) -> bool:
    expected = example.get("expected", {})
    assertions = example.get("assertions", {})
    if "action_not_in" in assertions:
        return decision_action not in assertions["action_not_in"]
    if "action" in expected:
        return decision_action == expected["action"]
    return True


def score(examples: list[dict[str, Any]], results: list[tuple[str, Any]]) -> dict[str, Any]:
    """Compute metrics for the evaluated examples and print a report.

    Returns the computed metrics dict so callers (tests) can assert on the
    numbers directly instead of parsing printed output.
    """
    evaluated = [(e, d) for (e, (status, d)) in zip(examples, results) if status == OK]
    skipped = [(e, status) for e, (status, _) in zip(examples, results) if status != OK]

    if skipped:
        print(f"Skipped {len(skipped)}/{len(examples)} examples (not runnable or errored):")
        for example, status in skipped:
            print(f"  - {example['id']}: {status}")
        print()

    if not evaluated:
        return {"evaluated": 0, "skipped": len(skipped)}

    correct_count = 0
    category_totals: dict[str, int] = defaultdict(int)
    category_correct: dict[str, int] = defaultdict(int)
    escalations_correct = 0
    escalations_needless = 0

    for example, decision in evaluated:
        expected = example.get("expected", {})
        category_ok = "category" not in expected or decision.category == expected["category"]
        severity_ok = "severity" not in expected or _severity_ok(
            decision.severity.value, expected["severity"]
        )
        action_ok = _action_matches(decision.action, example)
        queue_ok = True
        if decision.action == Action.ROUTE and "target_queue" in expected:
            queue_ok = decision.target_queue == expected["target_queue"]

        is_correct = category_ok and severity_ok and action_ok and queue_ok
        if is_correct:
            correct_count += 1

        category_totals[decision.category] += 1
        if is_correct:
            category_correct[decision.category] += 1

        if decision.action == Action.ESCALATE:
            expected_escalate = _action_matches(Action.ESCALATE, example)
            if expected_escalate:
                escalations_correct += 1
            else:
                escalations_needless += 1

    total = len(evaluated)
    accuracy = correct_count / total
    print(f"Evaluated: {total} examples")
    print(f"Overall accuracy: {correct_count}/{total} ({accuracy:.0%})")
    print()

    print("Per-category precision (of predictions in that category):")
    for category in sorted(category_totals):
        c_total = category_totals[category]
        c_correct = category_correct[category]
        print(f"  - {category}: {c_correct}/{c_total} ({c_correct / c_total:.0%})")
    print()

    total_escalations = escalations_correct + escalations_needless
    if total_escalations:
        print(
            f"Escalation rate: {escalations_correct}/{total_escalations} correct, "
            f"{escalations_needless}/{total_escalations} needless"
        )
    else:
        print("Escalation rate: no escalations issued")

    return {
        "evaluated": total,
        "skipped": len(skipped),
        "correct": correct_count,
        "accuracy": accuracy,
        "category_totals": dict(category_totals),
        "category_correct": dict(category_correct),
        "escalations_correct": escalations_correct,
        "escalations_needless": escalations_needless,
    }


async def main() -> int:
    examples = load_dataset()
    results = [await run_one(example) for example in examples]

    if examples and all(status == NOT_RUNNABLE for status, _ in results):
        print(
            f"Coordinator not implemented yet (Track B pending). "
            f"{len(examples)} fixtures loaded and schema-valid; 0 evaluated."
        )
        return 2

    score(examples, results)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
