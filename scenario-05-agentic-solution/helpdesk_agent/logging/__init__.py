"""Reasoning-chain logging (Track B).

Every decision must be replayable from the log alone: input, tool calls + results,
retries (count + error type), and the final decision. Prefer structured JSON lines.

See ../../CLAUDE.md ("Coordinator rules").
"""

# TODO(Track B): implement a structured logger (one JSON record per request).
