"""Standalone smoke test for the helpdesk tools (Track A).

Exercises every tool's success AND error path by calling the handlers directly —
no agent, no API key, no network. Run before Track B wires the tools in:

    python -m helpdesk_agent.tools.smoke_test

Exits non-zero if any case doesn't match its expected outcome.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Callable

from helpdesk_agent.tools import (
    check_queue_load,
    kb_lookup,
    lookup_asset,
    lookup_requester,
    route_ticket,
)


def _handler(tool_obj: Any) -> Callable[[dict[str, Any]], Any]:
    """Resolve the async handler from an SdkMcpTool wrapper (or a bare callable)."""
    if callable(tool_obj):
        return tool_obj
    for attr in ("handler", "func", "callback", "fn"):
        candidate = getattr(tool_obj, attr, None)
        if callable(candidate):
            return candidate
    raise TypeError(f"Could not resolve a callable handler from {tool_obj!r}")


async def _call(tool_obj: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await _handler(tool_obj)(args)


def _text(resp: dict[str, Any]) -> str:
    return resp["content"][0]["text"]


async def main() -> int:
    # Route writes to a throwaway file so the test never touches real artifacts.
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    tmp.close()
    os.environ["HELPDESK_ROUTE_LOG"] = tmp.name

    cases: list[tuple[str, Any, dict[str, Any], bool]] = [
        # (label, tool, args, expect_error)
        ("kb_lookup hit", kb_lookup, {"query": "I forgot my password and I'm locked out"}, False),
        ("kb_lookup security", kb_lookup, {"query": "I think I got a phishing email"}, False),
        ("kb_lookup no-match", kb_lookup, {"query": "zzz nonsense qqq"}, True),
        ("kb_lookup empty", kb_lookup, {"query": "   "}, True),
        ("lookup_requester hit", lookup_requester, {"email": "Dana.Okafor@acme-synthetic.example"}, False),
        ("lookup_requester missing", lookup_requester, {"email": "nobody@nowhere.example"}, True),
        ("lookup_requester bad", lookup_requester, {"email": "not-an-email"}, True),
        ("lookup_asset hit", lookup_asset, {"asset_tag": "lt-4471"}, False),
        ("lookup_asset missing", lookup_asset, {"asset_tag": "LT-0000"}, True),
        ("check_queue_load one", check_queue_load, {"queue": "network-ops"}, False),
        ("check_queue_load all", check_queue_load, {}, False),
        ("check_queue_load bad", check_queue_load, {"queue": "does-not-exist"}, True),
        (
            "route_ticket route",
            route_ticket,
            {
                "target_queue": "network-ops",
                "category": "network",
                "severity": "P3",
                "action": "route",
                "requester_email": "lin.wei@acme-synthetic.example",
                "summary": "VPN slow",
            },
            False,
        ),
        (
            "route_ticket route-missing-queue",
            route_ticket,
            {
                "target_queue": None,
                "category": "network",
                "severity": "P3",
                "action": "route",
                "requester_email": "lin.wei@acme-synthetic.example",
                "summary": "VPN slow",
            },
            True,
        ),
        (
            "route_ticket escalate-with-queue",
            route_ticket,
            {
                "target_queue": "security-incident",
                "category": "security",
                "severity": "P1",
                "action": "escalate",
                "requester_email": "marcus.bello@acme-synthetic.example",
                "summary": "suspected breach",
            },
            True,
        ),
    ]

    passed = 0
    failed = 0
    for label, tool_obj, args, expect_error in cases:
        resp = await _call(tool_obj, args)
        got_error = bool(resp.get("is_error"))
        ok = got_error == expect_error
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        detail = _text(resp).replace("\n", " ")[:90]
        print(f"[{status}] {label:34s} is_error={got_error!s:5} :: {detail}")

    # Confirm the one write actually landed.
    with open(tmp.name, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip()]
    write_ok = len(lines) == 1 and json.loads(lines[0]).get("status") is None  # log record has no 'status' key
    print(f"[{'PASS' if len(lines) == 1 else 'FAIL'}] route_ticket wrote exactly one record ({len(lines)})")
    if len(lines) != 1:
        failed += 1
    else:
        passed += 1

    os.unlink(tmp.name)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
