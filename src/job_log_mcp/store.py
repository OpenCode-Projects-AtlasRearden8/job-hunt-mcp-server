"""Plain-file storage layer for job applications.

Data lives in a single JSON file (default: ./data/joblog.json). All read/write
operations are serialized with a threading lock so the MCP server is safe to
use from its single async event loop while staying simple.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any

# Canonical application statuses.
STATUS_OPEN = "open"
STATUS_APPLIED = "applied"
STATUS_INTERVIEWING = "interviewing"
STATUS_OFFER = "offer"
STATUS_CLOSED = "closed"
STATUS_STALE = "stale"

VALID_STATUSES = (STATUS_OPEN, STATUS_APPLIED, STATUS_INTERVIEWING, STATUS_OFFER, STATUS_CLOSED)

JSON_FIELDS = (
    "id",
    "company",
    "role",
    "status",
    "url",
    "date_added",
    "date_applied",
    "last_contact",
    "next_action",
    "next_action_due",
    "contacts",
    "interview_feedback",
    "notes",
)

FREE_TEXT_FIELDS = ("company", "role", "status", "url", "date_added", "date_applied",
                    "last_contact", "next_action", "next_action_due", "contacts",
                    "interview_feedback", "notes")


def _today() -> date:
    """Today's date (separate function so tests can patch one place)."""
    return date.today()


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date string ('YYYY-MM-DD'); returns None for blank input."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    return date.fromisoformat(value)


def load_data(path: Path | None = None) -> dict[str, Any]:
    """Load the data file, creating the parent directory and file if needed."""
    path = path or default_data_path()
    if not path.exists():
        data: dict[str, Any] = {"applications": []}
        save_data(data, path)
        return data
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("applications"), list):
        raise ValueError(f"data file {path} is malformed; expected an object with an 'applications' list")
    if "next_id" not in raw:
        raw["next_id"] = 1
    return raw


def save_data(data: dict[str, Any], path: Path | None = None) -> None:
    """Write the data file atomically (temp file + rename)."""
    path = path or default_data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def default_data_path() -> Path:
    """Resolve the data file location from env override or default location."""
    env = os.environ.get("JOBHUNT_DATA_FILE")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent.parent / "data" / "joblog.json"


class JobLogStore:
    """Simple append/update store backed by one JSON file."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_data_path()
        self._lock = threading.Lock()
        self.data = load_data(self.path)

    def _persist(self) -> None:
        save_data(self.data, self.path)

    # ------------------------------------------------------------------ CRUD

    def add_application(self, record: dict[str, Any]) -> dict[str, Any]:
        """Add a new application with a fresh id and date_added = today."""
        with self._lock:
            rec = dict(record)
            rec["id"] = int(self.data.get("next_id", 1))
            self.data["next_id"] = rec["id"] + 1
            rec.setdefault("date_added", _today().isoformat())
            rec.setdefault("status", STATUS_OPEN)
            rec.setdefault("contacts", [])
            rec.setdefault("interview_feedback", [])
            rec["contacts"] = list(rec["contacts"])
            rec["interview_feedback"] = list(rec["interview_feedback"])
            self.data["applications"].append(rec)
            self._persist()
            return dict(rec)

    def get(self, app_id: int) -> dict[str, Any]:
        for rec in self.data["applications"]:
            if rec["id"] == app_id:
                return rec
        raise KeyError(app_id)

    def update(self, app_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        rec = self.get(app_id)
        for key, value in updates.items():
            if key in JSON_FIELDS and key != "id":
                if key in ("contacts", "interview_feedback") and isinstance(value, str):
                    value = [line.strip() for line in value.splitlines() if line.strip()]
                rec[key] = value
        self._persist()
        return rec

    def delete(self, app_id: int) -> bool:
        before = len(self.data["applications"])
        self.data["applications"] = [r for r in self.data["applications"] if r["id"] != app_id]
        removed = len(self.data["applications"]) < before
        if removed:
            self._persist()
        return removed

    def list_applications(self) -> list[dict[str, Any]]:
        return list(self.data["applications"])

    # ------------------------------------------------------- status & gates

    def set_status(self, app_id: int, status: str, when: str | None = None) -> dict[str, Any]:
        """Change status plus its derived side-effect dates."""
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}; must be one of {', '.join(VALID_STATUSES)}")
        rec = self.get(app_id)
        rec["status"] = status
        if status == STATUS_APPLIED and when:
            rec["date_applied"] = when
            if not rec.get("date_added"):
                rec["date_added"] = when
        if status in (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_CLOSED):
            rec["last_contact"] = when or _today().isoformat()
        self._persist()
        return rec

    def add_feedback(self, app_id: int, date_str: str, notes: str) -> dict[str, Any]:
        rec = self.get(app_id)
        rec.setdefault("interview_feedback", []).append({"date": date_str, "notes": notes})
        rec["last_contact"] = date_str
        if rec.get("status") in (STATUS_OPEN, STATUS_APPLIED):
            rec["status"] = STATUS_INTERVIEWING
        self._persist()
        return rec

    def add_contact(self, app_id: int, name: str, role: str = "", email: str = "") -> dict[str, Any]:
        rec = self.get(app_id)
        rec.setdefault("contacts", []).append(
            {"name": name, "role": role, "email": email}
        )
        self._persist()
        return rec

    # ------------------------------------------------------------- staleness

    def to_plain_text(self, apps: list[dict[str, Any]] | None = None) -> str:
        """Render applications as chat-ready plain text (one per line)."""
        apps = apps if apps is not None else self.list_applications()
        if not apps:
            return "No applications recorded."
        lines = []
        for rec in apps:
            lines.append(self.format_application(rec))
        return "\n".join(lines)

    @staticmethod
    def format_application(rec: dict[str, Any]) -> str:
        stale = is_stale(rec)["stale"]
        flag = " [STALE]" if stale else ""
        contact_str = "; ".join(
            c.get("name", "?") + (" (" + c["role"] + ")" if c.get("role") else "")
            for c in rec.get("contacts", [])
        ) or "-"
        return (
            "#{id} {company} - {role} | status={status} | applied={applied}"
            " | last_contact={last} | next={next} (due {due}) | contacts: {contacts}{flag}".format(
                id=rec.get("id", "?"),
                company=rec.get("company", "unknown"),
                role=rec.get("role", "unknown"),
                status=rec.get("status", "?"),
                applied=rec.get("date_applied") or "n/a",
                last=rec.get("last_contact") or "n/a",
                next=rec.get("next_action") or "n/a",
                due=rec.get("next_action_due") or "n/a",
                contacts=contact_str,
                flag=flag,
            )
        )


def stale_days_threshold(rec: dict[str, Any]) -> int:
    """How many days without contact before an application is considered stale."""
    if rec.get("status") == STATUS_INTERVIEWING:
        return 10
    if rec.get("status") == STATUS_OFFER:
        return 30
    if rec.get("status") == STATUS_CLOSED:
        return -1  # closed applications can never be stale
    return 7  # open / applied default


def is_stale(rec: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    """Return the staleness decision for one application.

    A record is stale when:
      - its status is not 'closed',
      - it has no next_action_due in the future, and
      - the more recent of (last_contact, date_applied) - or date_added for
        brand-new leads without an applied date - is older than the
        status-specific threshold.
    """
    today = as_of or _today()
    status = rec.get("status", STATUS_OPEN)
    threshold = stale_days_threshold(rec)
    activity_fields = ("last_contact", "date_applied") if (
        rec.get("last_contact") or rec.get("date_applied")
    ) else ("date_added",)
    activity_dates = [
        parse_date(rec.get(field)) for field in activity_fields
    ]
    activity_dates = [d for d in activity_dates if d is not None]
    recent = max(activity_dates) if activity_dates else None
    days = (today - recent).days if recent else None
    due = parse_date(rec.get("next_action_due"))
    overdue = due is not None and due < today
    has_future_action = due is not None and due >= today
    stale = (
        status != STATUS_CLOSED
        and not has_future_action
        and days is not None
        and days > threshold
    )
    return {
        "stale": stale,
        "days_since_contact": days,
        "threshold": threshold,
        "overdue_next_action": overdue,
        "has_next_action": due is not None,
    }


def applications_by_week(store: JobLogStore, week_start: date, week_end: date) -> list[dict[str, Any]]:
    """Applications with a next_action_due inside the given window, or overdue."""
    out = []
    for rec in store.list_applications():
        due = parse_date(rec.get("next_action_due"))
        if due and week_start <= due <= week_end:
            out.append(rec)
            continue
        if is_stale(rec, as_of=week_end)["overdue_next_action"]:
            out.append(rec)
    return out
