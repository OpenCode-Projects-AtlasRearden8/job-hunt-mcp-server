"""MCP server exposing job-log tools over stdio.

Run from the repo root:
    python -m job_log_mcp.server        (if src/ is on the path)
or set PYTHONPATH=src first. See README for details.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from mcp.server.mcpserver import MCPServer

from .store import (
    JobLogStore,
    _today,
    applications_by_week,
    is_stale,
    parse_date,
)

server = MCPServer(
    name="job-hunt-mcp-server",
    title="Job Hunt Log",
    description=(
        "Local plain-file log of job applications with status, dates, contacts and "
        "interview feedback. Helps you answer: what is due this week, what went stale, "
        "and draft gentle follow-ups from my own notes."
    ),
    instructions=(
        "Use list_applications to see everything, what_is_due_this_week for the weekly plan, "
        "find_stale_applications for anything that needs a nudge, and draft_follow_up to write "
        "a gentle follow-up email from the stored notes. Add or update records with the "
        "add_application / update_application / set_status / add_contact / add_interview_feedback tools. "
        "All data stays in a local JSON file: data/joblog.json (override with JOBHUNT_DATA_FILE)."
    ),
)


def _store() -> JobLogStore:
    return JobLogStore()


def _fmt_stale_report(apps: list[dict]) -> str:
    lines = []
    for rec in apps:
        s = is_stale(rec)
        if s["stale"] or s["overdue_next_action"]:
            reason = []
            if s["stale"]:
                reason.append(
                    f"no contact in {s['days_since_contact']} days (limit {s['threshold']})"
                )
            if s["overdue_next_action"]:
                reason.append("next action is overdue")
            lines.append(
                f"#{rec['id']} {rec.get('company')} - {rec.get('role')}: " + "; ".join(reason)
            )
    return "\n".join(lines) if lines else "Nothing is stale right now. Good pace."


@server.tool()
def add_application(
    company: str,
    role: str,
    status: str = "open",
    url: str = "",
    date_applied: str = "",
    next_action: str = "",
    next_action_due: str = "",
    notes: str = "",
) -> str:
    """Record a new job application. Dates use YYYY-MM-DD."""
    rec = _store().add_application(
        {
            "company": company,
            "role": role,
            "status": status,
            "url": url,
            "date_applied": date_applied,
            "next_action": next_action,
            "next_action_due": next_action_due,
            "notes": notes,
        }
    )
    return f"Added #{rec['id']}: {company} - {role} (status {rec['status']})."


@server.tool()
def list_applications(status: str = "") -> str:
    """List applications as chat-ready plain text; optionally filter by status."""
    apps = _store().list_applications()
    if status:
        apps = [a for a in apps if a.get("status") == status]
    return _store().to_plain_text(apps)


@server.tool()
def update_application(app_id: int, field: str, value: str) -> str:
    """Update one field of an application (company, role, url, notes, next_action, next_action_due, status)."""
    store = _store()
    rec = store.update(app_id, {field: value})
    return f"Updated #{rec['id']}: {field} = {value}"


@server.tool()
def set_status(app_id: int, status: str, when: str = "") -> str:
    """Set the status. When it flips to applied/interviewing/offer/closed, contact dates update automatically."""
    rec = _store().set_status(app_id, status, when or None)
    return (
        f"#{rec['id']} {rec.get('company')} is now '{rec['status']}' "
        f"(last contact: {rec.get('last_contact') or 'n/a'})."
    )


@server.tool()
def add_contact(app_id: int, name: str, role: str = "", email: str = "") -> str:
    """Add a contact person to an application (recruiter, hiring manager...)."""
    rec = _store().add_contact(app_id, name, role, email)
    return f"Added contact {name} to #{rec['id']}."


@server.tool()
def add_interview_feedback(app_id: int, date_str: str, notes: str) -> str:
    """Record interview feedback: the interview date (YYYY-MM-DD) plus your notes."""
    rec = _store().add_feedback(app_id, date_str, notes)
    return f"Recorded feedback for #{rec['id']} on {date_str}."


@server.tool()
def what_is_due_this_week(days: int = 7) -> str:
    """Applications whose next action falls in the next `days` days (due dates or overdue)."""
    store = _store()
    today = _today()
    week_end = today + timedelta(days=max(1, days))
    apps = applications_by_week(store, today, week_end)
    if not apps:
        return f"Nothing due between {today.isoformat()} and {week_end.isoformat()}."
    lines = [f"Due between {today.isoformat()} and {week_end.isoformat()}:"]
    for rec in apps:
        due = parse_date(rec.get("next_action_due"))
        note = f"due {due.isoformat()}" if due else "past-due next action"
        lines.append(f"- #{rec['id']} {rec.get('company')} - {rec.get('role')}: {rec.get('next_action') or 'follow up'} ({note})")
    return "\n".join(lines)


@server.tool()
def find_stale_applications() -> str:
    """Applications with no recent contact and no upcoming next-action; the nudge list."""
    apps = _store().list_applications()
    return _fmt_stale_report(apps)


@server.tool()
def draft_follow_up(app_id: int, tone: str = "gentle") -> str:
    """Draft a gentle follow-up email for one application, using the stored notes and contacts."""
    store = _store()
    rec = store.get(app_id)
    contact = (rec.get("contacts") or [{}])[0]
    name = contact.get("name") or "Hiring team"
    notes = (rec.get("notes") or "").strip()
    feedback = rec.get("interview_feedback") or []
    last = rec.get("last_contact") or rec.get("date_applied") or "our last check-in"
    lines = [
        f"Subject: Following up - {rec.get('role')} at {rec.get('company')}",
        "",
        f"Hi {name},",
        "",
        f"Hope your week is going well. I wanted to send a quick, friendly note about "
        f"the {rec.get('role')} position at {rec.get('company')} (last touch: {last}). "
        f"I'm still very interested and happy to help if anything else would be useful.",
    ]
    if notes:
        lines.append("")
        lines.append(f"From my notes: {notes}")
    if feedback:
        lines.append("")
        latest = feedback[-1]
        lines.append(f"Since our conversation on {latest['date']}, one thing stuck with me: {latest['notes']}")
    lines += ["", "No need to reply today - just a gentle nudge whenever it's convenient.", "", "Warm regards,", "Dylan"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Job-hunt MCP server (stdio)")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    args = parser.parse_args()
    if args.version:
        import job_log_mcp

        print(f"job-hunt-mcp-server {job_log_mcp.__version__}")
        return
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
