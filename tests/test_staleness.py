"""Tests for staleness checks and the due-this-week window."""

from datetime import date

from job_log_mcp.store import (
    STATUS_APPLIED,
    STATUS_CLOSED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_OPEN,
    JobLogStore,
    applications_by_week,
    is_stale,
    stale_days_threshold,
)

AS_OF = date(2026, 11, 7)


def make_record(status=STATUS_APPLIED, last_contact="2026-11-01", **extra):
    rec = {
        "id": 1,
        "company": "Test Co",
        "role": "Role",
        "status": status,
        "date_added": "2026-10-01",
        "date_applied": "2026-11-01",
        "last_contact": last_contact,
        "next_action": "",
        "next_action_due": "",
        "contacts": [],
        "interview_feedback": [],
        "notes": "",
    }
    rec.update(extra)
    return rec


def test_thresholds_by_status():
    assert stale_days_threshold(make_record(STATUS_OPEN)) == 7
    assert stale_days_threshold(make_record(STATUS_APPLIED)) == 7
    assert stale_days_threshold(make_record(STATUS_INTERVIEWING)) == 10
    assert stale_days_threshold(make_record(STATUS_OFFER)) == 30
    assert stale_days_threshold(make_record(STATUS_CLOSED)) == -1


def test_not_stale_within_threshold():
    assert is_stale(make_record(last_contact="2026-11-01"), as_of=AS_OF) == {
        "stale": False,
        "days_since_contact": 6,
        "threshold": 7,
        "overdue_next_action": False,
        "has_next_action": False,
    }


def test_stale_after_threshold():
    result = is_stale(
        make_record(last_contact="2026-10-30", date_applied="2026-10-25"), as_of=AS_OF
    )
    assert result["stale"] is True
    assert result["days_since_contact"] == 8


def test_closed_is_never_stale():
    rec = make_record(STATUS_CLOSED, last_contact="2026-08-01")
    assert is_stale(rec, as_of=AS_OF)["stale"] is False


def test_future_next_action_postpones_staleness():
    rec = make_record(last_contact="2026-10-20", next_action_due="2026-11-20")
    result = is_stale(rec, as_of=AS_OF)
    assert result["stale"] is False
    assert result["has_next_action"] is True


def test_past_due_next_action_marks_overdue():
    rec = make_record(last_contact="2026-11-06", next_action_due="2026-11-05")
    result = is_stale(rec, as_of=AS_OF)
    assert result["stale"] is False  # fresh contact
    assert result["overdue_next_action"] is True


def test_interviewing_uses_longer_threshold():
    # 9 days since contact would be stale for open/applied, not for interviewing.
    rec = make_record(STATUS_INTERVIEWING, last_contact="2026-10-29", date_applied="2026-10-25")
    assert is_stale(rec, as_of=AS_OF)["stale"] is False
    rec_applied = make_record(STATUS_APPLIED, last_contact="2026-10-29", date_applied="2026-10-25")
    assert is_stale(rec_applied, as_of=AS_OF)["stale"] is True


def test_offer_uses_longest_threshold():
    rec = make_record(STATUS_OFFER, last_contact="2026-10-05", date_applied="2026-10-01")
    assert is_stale(rec, as_of=AS_OF)["stale"] is True  # 33 days > 30

    rec = make_record(STATUS_OFFER, last_contact="2026-10-15", date_applied="2026-10-01")
    assert is_stale(rec, as_of=AS_OF)["stale"] is False  # 23 days


def test_reference_uses_most_recent_date():
    # last_contact is old, but date_applied is recent -> not stale.
    rec = make_record(last_contact="2020-01-01", date_applied="2026-11-06")
    assert is_stale(rec, as_of=AS_OF)["stale"] is False


def test_due_this_week_window(tmp_path):
    store = JobLogStore(path=tmp_path / "joblog.json")
    a = store.add_application(
        {"company": "A", "role": "R", "next_action": "Follow up", "next_action_due": "2026-11-09"}
    )
    store.add_application(
        {"company": "B", "role": "R", "next_action": "Follow up", "next_action_due": "2027-01-20"}
    )
    due = applications_by_week(store, AS_OF, date(2026, 11, 14))
    assert [r["id"] for r in due] == [a["id"]]


def test_due_this_week_includes_overdue(tmp_path):
    store = JobLogStore(path=tmp_path / "joblog.json")
    a = store.add_application(
        {"company": "A", "role": "R", "next_action": "Send thank-you", "next_action_due": "2026-11-01"}
    )
    due = applications_by_week(store, AS_OF, date(2026, 11, 14))
    assert [r["id"] for r in due] == [a["id"]]


def test_stale_report_text(tmp_path):
    store = JobLogStore(path=tmp_path / "joblog.json")
    rec = store.add_application({"company": "Quiet Co", "role": "R"})
    store.update(rec["id"], {"date_added": "2026-10-01", "date_applied": "2026-10-10"})
    report = store.to_plain_text(store.list_applications())
    assert "[STALE]" in report
    detail = "\n".join(
        line for line in report.splitlines() if line.startswith("#")
    )
    assert "Quiet Co" in detail and "stale" not in detail.split("status=")[0].split("|")[0]
