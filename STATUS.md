# STATUS.md

## What was built

`job-hunt-mcp-server` - a local, plain-file MCP server for a personal job-hunt
log. Records job applications with status, dates, contacts, and interview
feedback in a single JSON file (`data/joblog.json`, override with
`JOBHUNT_DATA_FILE`), and exposes nine MCP tools that return chat-ready plain
text so an agent can answer "what is due this week?", "what went stale?", and
draft gentle follow-ups from your own notes.

Project layout:

- `src/job_log_mcp/store.py` - storage ("one JSON file"), status math, staleness rules, plain-text rendering
- `src/job_log_mcp/server.py` - `MCPServer` (mcp SDK, stdio transport) with the 9 tools
- `tests/` - status math, staleness checks, and full end-to-end tool workflows
- `README.md`, `LICENSE` (MIT, Copyright (c) 2026 Asdale Dynamics, LLC), `pyproject.toml`

Tools: `add_application`, `list_applications`, `update_application`,
`set_status`, `add_contact`, `add_interview_feedback`,
`what_is_due_this_week`, `find_stale_applications`, `draft_follow_up`.

## How to run

```bash
pip install .
jobhunt-mcp              # MCP server over stdio; point your agent here
jobhunt-mcp --version    # prints job-hunt-mcp-server 0.1.0
```

Data: `data/joblog.json` (auto-created). Set `JOBHUNT_DATA_FILE` to relocate.

## Verification results

- `pytest`: **25 passed** (status side-effect dates; staleness thresholds by
  status, future next-actions postponing staleness, overdue detection; two
  MCP end-to-end workflows via `server.call_tool`).
- `pyflakes src tests`: clean.
- Live stdio smoke test with the MCP Python client (`stdio_client` +
  `ClientSession`): `initialize`, `list_tools` (all 9 tools listed), then
  add/status/stale/due/draft calls all returned expected plain-text results.
  Confirmed a record applied Oct 1 with no pending next action reports
  "no contact in 37 days (limit 7)".

## Known gaps

- No fuzzy matching or de-duplication of company/role names.
- `what_is_due_this_week` uses calendar days (default 7), not workdays.
- No archiving/backup commands; users manage `data/joblog.json` manually.
- Follow-up drafts are plain templates built from stored notes - not sent
  anywhere (email sending is intentionally out of scope).
- Only stdio transport; no HTTP mode.
