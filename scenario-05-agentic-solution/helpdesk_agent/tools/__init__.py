"""Custom tools (Track A).

Exposed to the agent via create_sdk_mcp_server(name="helpdesk", ...); the agent
references them as mcp__helpdesk__<tool_name>.

Planned tools (~5). Reads are pure/side-effect-free; only route_ticket writes:
  - kb_lookup         (knowledge lookup)
  - lookup_requester  (system-of-record read)
  - lookup_asset      (system-of-record read)
  - check_queue_load  (read helper for routing)
  - route_ticket      (the write action)

Each tool's description must teach WHEN to use it and what it does NOT do, with
input formats and an example query. Errors return a structured response
(is_error=True + reason code + guidance), never a raw string.

See ../../CLAUDE.md ("Tool design rules").
"""

# TODO(Track A): implement the tools above and assemble the helpdesk MCP server.
