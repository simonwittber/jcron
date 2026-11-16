import json
import subprocess
from datetime import datetime, timedelta

import pytest

from jcron import hook, paths, stale, store
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


@pytest.fixture(autouse=True)
def no_report_yet():
    (paths.home() / "last-stale-report.txt").unlink()


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


def reasons_by_id(at):
    return {job.id: why for job, why in stale.stale_jobs(at)}


def test_folder_gone(tmp_path):
    job = store.add("reminder", "x", at=T0 + timedelta(days=1), base=T0, folder=str(tmp_path / "gone"))
    assert reasons_by_id(T0)[job.id] == ["its folder is gone"]


def test_branch_gone(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "commit", "--allow-empty", "-m", "start")
    kept = store.add("reminder", "kept", at=T0 + timedelta(days=1), base=T0, folder=str(tmp_path), branch="main")
    gone = store.add("reminder", "gone", at=T0 + timedelta(days=1), base=T0, folder=str(tmp_path), branch="merged-and-deleted")
    found = reasons_by_id(T0)
    assert kept.id not in found
    assert found[gone.id] == ["branch merged-and-deleted is gone"]


def test_overdue_more_than_two_weeks(tmp_path):
    job = store.add("reminder", "x", at=T0, base=T0, folder=str(tmp_path))
    assert reasons_by_id(T0 + timedelta(days=14)) == {}
    assert "overdue since" in reasons_by_id(T0 + timedelta(days=15))[job.id][0]


def test_claimed_and_never_finished(tmp_path):
    job = store.add("reminder", "x", at=T0, base=T0, folder=str(tmp_path))
    store.claim(job.id, "s", at=T0)
    assert "never finished" in reasons_by_id(T0 + timedelta(days=15))[job.id][0]


def test_expired_todo(tmp_path):
    job = store.add("todo", "x", base=T0, folder=str(tmp_path), expires=T0 + timedelta(days=1))
    assert "expired" in reasons_by_id(T0 + timedelta(days=2))[job.id][0]


def test_report_runs_once_a_week(tmp_path):
    store.add("reminder", "x", at=T0 + timedelta(days=30), base=T0, folder=str(tmp_path / "gone"))
    assert len(stale.weekly(T0)) == 1
    assert stale.weekly(T0 + timedelta(days=6)) == []
    assert len(stale.weekly(T0 + timedelta(days=7))) == 1


def test_hook_shows_report_at_session_start_from_any_folder(tmp_path):
    job = store.add("reminder", "x", at=T0 + timedelta(days=30), base=T0, folder=str(tmp_path / "gone"))
    (tmp_path / "elsewhere").mkdir()
    prompt = json.dumps({"session_id": "s", "hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path / "elsewhere")})
    assert hook.run(prompt, T0) == ""
    start = json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": str(tmp_path / "elsewhere")})
    out = json.loads(hook.respond(start, T0))
    assert "1 stale job(s)" in out["systemMessage"]
    assert job.id in out["hookSpecificOutput"]["additionalContext"]
    assert hook.respond(start, T0) == ""
