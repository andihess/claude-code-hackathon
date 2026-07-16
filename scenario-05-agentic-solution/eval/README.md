# Eval harness (Track C)

Runs the coordinator over a labeled dataset and scores its decisions.

- `dataset.jsonl` — 12 labeled examples joined by `id` to `../fixtures/tickets/*.json`.
  Each line: `{"id", "ticket_file", "expected": {category, severity, action, target_queue},
  "notes"}`. Boundary/judgment-call rows use an `assertions` block (e.g.
  `"action_not_in": ["auto_resolve"]`) instead of a single exact action.
- `run_eval.py` — loads the dataset, runs `triage()` per example, compares to expected,
  prints metrics. Run with `python eval/run_eval.py` from `scenario-05-agentic-solution/`
  (or from anywhere — paths are resolved relative to the script).
- `test_run_eval_harness.py` — pytest smoke test that mocks `triage()` so the scoring
  math can be validated without `ANTHROPIC_API_KEY` or a working coordinator.

Metrics implemented: overall accuracy, per-category precision, and escalation rate
(correct vs. needless). Adversarial set + false-confidence rate are follow-ups (Ch.6/7).

## Current status

`helpdesk_agent.coordinator.triage()` is still a stub (Track B in progress), so
`run_eval.py` currently loads and validates all 12 fixtures, then exits with status 2 and
a message saying the coordinator isn't runnable yet — it does not crash on
`NotImplementedError`. Once Track B lands, re-run it for real metrics.
