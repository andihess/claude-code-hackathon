"""Coordinator agent (Track B).

Loop: ingest -> classify -> enrich (kb + system-of-record) -> decide -> act -> log.
Uses the Claude Agent SDK query()/ClaudeSDKClient with output_format bound to
DECISION_JSON_SCHEMA, wrapped in the validation-retry loop.

See ../../CLAUDE.md ("Coordinator rules") for the contract.
"""

from __future__ import annotations

# TODO(Track B): implement the coordinator.
# - build ClaudeAgentOptions (model="sonnet", system_prompt, mcp_servers, output_format)
# - wire the helpdesk MCP server from tools/
# - run the validation-retry loop (validation.py), max 3 retries
# - emit the reasoning-chain log (logging/) so every decision is replayable


async def triage(request: dict) -> "object":
    """Triage one inbound request and return a validated TriageDecision.

    Args:
        request: {subject, body, channel, requester_email}
    """
    raise NotImplementedError("Track B: implement the coordinator loop.")
