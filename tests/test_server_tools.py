"""Integration test: every tool on the MCP server runs end-to-end against a temp data file."""

import asyncio
import json
from datetime import date

import pytest

import job_log_mcp.server as srv
from job_log_mcp.store import JobLogStore


class FakeContext:
    """Minimal request context shim for calling server tools directly."""

    def __init__(self):
        self.request_context = None


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    path = tmp_path / "data" / "joblog.json"
    monkeypatch.setenv("JOBHUNT_DATA_FILE", str(path))
    return path


@pytest.fixture
def call_tool(data_file):
    def _call(name, kwargs=None):
        kwargs = kwargs or {}
        result = asyncio.run(srv.server.call_tool(name, kwargs))
        assert result
        texts = [getattr(c, "text", "") for c in result.content]
        return "\n".join(texts)

    return _call


def test_full_workflow(call_tool, data_file):
    out = call_tool("add_application", {
        "company": "Riverbend Health",
        "role": "RN AI Educator",
        "next_action": "Send thank-you note",
        "next_action_due": date.today().isoformat(),
        "notes": "Mention bedflow dashboard idea",
    })
    assert "Added #1" in out

    out = call_tool("add_application", {"company": "Quiet Co", "role": "Coordinator"})
    assert "Added #2" in out

    call_tool("add_contact", {"app_id": 1, "name": "Morgan", "role": "Recruiter", "email": ""})
    call_tool("set_status", {"app_id": 1, "status": "interviewing"})
    call_tool("add_interview_feedback", {"app_id": 1, "date_str": "2026-11-01", "notes": "Great panel"})

    out = call_tool("list_applications")
    assert "Riverbend Health" in out and "Quiet Co" in out

    out = call_tool("what_is_due_this_week")
    assert "Riverbend" in out  # due today

    # Make Quiet Co look old so it shows up as stale.
    JobLogStore(data_file).update(
        2, {"date_added": "2026-10-01", "date_applied": "2026-10-05"}
    )
    out = call_tool("find_stale_applications")
    assert "Quiet Co" in out  # unchanged since October -> stale

    out = call_tool("draft_follow_up", {"app_id": 2})
    assert "Quiet Co" in out and "Subject:" in out and "no need to reply today" in out.lower()

    stored = json.loads(data_file.read_text(encoding="utf-8"))
    assert stored["next_id"] == 3


def test_update_and_filters(call_tool):
    call_tool("add_application", {"company": "A", "role": "R"})
    out = call_tool("update_application", {"app_id": 1, "field": "notes", "value": "remote role"})
    assert "Updated" in out
    out = call_tool("list_applications", {"status": "applied"})
    assert out.strip() == "No applications recorded."
    out = call_tool("list_applications")
    assert "A - R" in out
