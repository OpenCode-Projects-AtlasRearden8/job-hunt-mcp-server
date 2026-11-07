"""Tests for status math: set_status side-effect dates and feedback/contact flows."""

import pytest

from job_log_mcp.store import (
    STATUS_APPLIED,
    STATUS_CLOSED,
    STATUS_INTERVIEWING,
    STATUS_OPEN,
    JobLogStore,
)


def make_store(tmp_path):
    return JobLogStore(path=tmp_path / "joblog.json")


def new_app(store, **kwargs):
    defaults = {"company": "Test Co", "role": "Nurse Informatics", "notes": "good vibes"}
    defaults.update(kwargs)
    return store.add_application({k: v for k, v in defaults.items() if v is not None})


def test_default_status_is_open(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    assert rec["status"] == STATUS_OPEN
    assert rec["date_added"]  # stamped


def test_invalid_status_rejected(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    with pytest.raises(ValueError):
        store.set_status(rec["id"], "dreaming")
    assert store.get(rec["id"])["status"] == STATUS_OPEN


def test_set_status_applied_stamps_date_applied(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    store.set_status(rec["id"], STATUS_APPLIED, when="2026-11-01")
    got = store.get(rec["id"])
    assert got["status"] == STATUS_APPLIED
    assert got["date_applied"] == "2026-11-01"


def test_set_status_interviewing_stamps_last_contact(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store, date_applied="2026-10-01")
    store.set_status(rec["id"], STATUS_INTERVIEWING, when="2026-11-03")
    got = store.get(rec["id"])
    assert got["status"] == STATUS_INTERVIEWING
    assert got["last_contact"] == "2026-11-03"
    assert got["date_applied"] == "2026-10-01"  # untouched by non-applied statuses


def test_set_status_closed_stamps_last_contact(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store, date_applied="2026-10-01")
    store.set_status(rec["id"], STATUS_CLOSED)
    got = store.get(rec["id"])
    assert got["last_contact"]  # stamped
    assert got["date_applied"] == "2026-10-01"


def test_add_feedback_flips_to_interviewing_and_stamps_last_contact(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    store.add_feedback(rec["id"], "2026-11-05", "Panel asked about washouts; bring QI data.")
    got = store.get(rec["id"])
    assert got["status"] == STATUS_INTERVIEWING
    assert got["last_contact"] == "2026-11-05"
    assert got["interview_feedback"] == [
        {"date": "2026-11-05", "notes": "Panel asked about washouts; bring QI data."}
    ]


def test_add_feedback_keeps_closed_closed(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    store.set_status(rec["id"], STATUS_CLOSED)
    store.add_feedback(rec["id"], "2026-11-05", "Rejection follow-up chit-chat.")
    assert store.get(rec["id"])["status"] == STATUS_CLOSED


def test_add_contact(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store)
    store.add_contact(rec["id"], "Morgan Reyes", "Recruiter", "morgan@example.com")
    got = store.get(rec["id"])
    assert got["contacts"] == [
        {"name": "Morgan Reyes", "role": "Recruiter", "email": "morgan@example.com"}
    ]


def test_delete_and_persistence(tmp_path):
    path = tmp_path / "joblog.json"
    store = JobLogStore(path=path)
    rec = new_app(store)
    assert JobLogStore(path=path).get(rec["id"])["company"] == "Test Co"
    store.delete(rec["id"])
    with pytest.raises(KeyError):
        JobLogStore(path=path).get(rec["id"])


def test_ids_increment(tmp_path):
    store = make_store(tmp_path)
    a = new_app(store, company="A")
    b = new_app(store, company="B")
    assert b["id"] == a["id"] + 1


def test_plain_text_output(tmp_path):
    store = make_store(tmp_path)
    rec = new_app(store, company="Riverbend Health", role="RN AI Educator")
    text = store.to_plain_text([store.get(rec["id"])])
    assert "#1 Riverbend Health - RN AI Educator" in text
    assert "status=open" in text
