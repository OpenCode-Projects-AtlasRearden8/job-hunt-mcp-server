# job-hunt-mcp-server

A small, local-first MCP (Model Context Protocol) server that keeps your job
hunt in plain files. Record applications with status, dates, contacts, and
interview feedback, then ask your AI agent things like:

- "What is due this week?"
- "Which applications went stale?"
- "Draft a gentle follow-up from my notes for that one."

Everything stays in a single local JSON file (`data/joblog.json`, or wherever
`JOBHUNT_DATA_FILE` points). No cloud, no accounts, no API keys. Results come
back as chat-ready plain text you can read, paste, or edit.

Part of the Asdale Dynamics, LLC toolbox. Partners in spirit (separate projects):
*job-application-tracker-webapp* (visual kanban board) and
*free-interview-prep-pack* (interview practice kit). This one is the quiet,
text-file logbook.

## Who it's for

Built by [Dylan Asdale](https://dylanasdale.github.io) of Asdale Dynamics, LLC -
beginner-friendly AI education, plain English, step by step, never condescending.

## Install

Requires Python 3.10+.

```bash
pip install .
```

That installs the `jobhunt-mcp` command and the `mcp` SDK dependency.

## Run (as a local MCP server)

```bash
jobhunt-mcp              # stdio transport, ready for your agent
# or:
python -m job_log_mcp.server
```

Point your MCP-capable agent (Claude Desktop, opencode, etc.) at the command
with stdio transport. Example opencode config:

```json
{
  "mcp": {
    "jobhunt": {
      "type": "local",
      "command": ["jobhunt-mcp"]
    }
  }
}
```

## Tools your agent gets

| Tool | What it does |
| --- | --- |
| `add_application` | Record a new application (company, role, status, dates, notes). |
| `list_applications` | Everything in the log as plain text, optionally filtered by status. |
| `update_application` | Change one field of a record. |
| `set_status` | Move status and let the server stamp contact dates automatically. |
| `add_contact` | Attach a recruiter / hiring manager to an application. |
| `add_interview_feedback` | Record interview date + your own feedback notes. |
| `what_is_due_this_week` | Next actions due in the window (including overdue). |
| `find_stale_applications` | No recent contact and no scheduled next action - the nudge list. |
| `draft_follow_up` | A gentle follow-up email drafted from the stored notes. |

## How staleness is decided

Plain rules, no magic:

- `open` / `applied`: stale after 7 days without contact.
- `interviewing`: stale after 10 days.
- `offer`: stale after 30 days.
- `closed`: never stale.
- A scheduled future `next_action_due` postpones staleness; a past-due one
  shows as overdue.

## Data

`data/joblog.json` - one file, human-readable, easy to back up or grep.
Test fixture data lives in `tests/`, never real application data.

## Run the tests

```bash
pip install .[test]
pytest
```

Covers the status math (side-effect dates when moving between statuses) and
the staleness rules from `store.py`.

## Privacy & security

Local files only. No network calls, no telemetry, no API keys, no personal
data shipped with the project. Keep your `data/` folder backed up where you
like, but out of git if it holds your real job hunt.

## License

MIT - see `LICENSE`. Copyright (c) 2026 Asdale Dynamics, LLC.
