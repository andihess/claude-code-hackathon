# Eval harness (Track C)

Runs the coordinator over a labeled dataset and scores its decisions.

- `dataset.jsonl` — labeled examples: input + expected decision (category, severity, action).
- `run_eval.py` — runs `triage()` per example, compares to expected, prints metrics.

Metrics to start with: overall accuracy, per-category precision, and escalation
rate (correct vs. needless). Adversarial set + false-confidence rate are follow-ups
(Ch.6/7).

TODO(Track C): build the runner and a first labeled dataset.
