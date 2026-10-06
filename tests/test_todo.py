import json
from datetime import datetime, timedelta

import pytest

from jcron import display, hook, paths, store
from jcron.store import JcronError
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


def add_todo(title="Fix the flaky test", folder="C:/work/proj", **kw):
    return store.add("todo", title, base=T0, folder=folder, branch="main", **kw)


def session_start(cwd):
    return json.dumps({"session_id": "abc", "hook_event_name": "SessionStart", "cwd": cwd})


def test_todo_expires_in_30_days_by_default():
    job = add_todo()
    assert job.due is None
    assert job.expires == T0 + timedelta(days=30)
    assert job.branch == "main"


def test_todo_takes_no_due_time():
    with pytest.raises(JcronError, match="no due time"):
        add_todo(at=T0)


def test_global_todo_keeps_branch_but_no_folder():
    job = add_todo(global_todo=True)
    assert job.folder is None and job.branch == "main"


def test_only_todos_can_be_global():
    with pytest.raises(JcronError, match="only TODOs"):
        store.add("reminder", "x", at=T0, base=T0, global_todo=True)


def test_todos_match_folder_plus_global():
    mine = add_todo("mine", folder=str(paths.home() / "proj"))
    shared = add_todo("shared", global_todo=True)
    add_todo("elsewhere", folder=str(paths.home() / "other"))
    found = {j.id for j in store.todos(str(paths.home() / "proj"), T0)}
    assert found == {mine.id, shared.id}
    assert len(store.todos(None, T0)) == 3


def test_todos_show_in_subfolders_only():
    job = add_todo(folder=str(paths.home() / "proj"))
    assert [j.id for j in store.todos(str(paths.home() / "proj" / "src" / "deep"), T0)] == [job.id]
    assert store.todos(str(paths.home()), T0) == []
    assert store.todos(str(paths.home() / "proj-old"), T0) == []


def test_todo_states():
    job = add_todo(expires=T0 + timedelta(days=10))
    assert store.todo_state(job, T0) == "todo"
    assert store.todo_state(job, T0 + timedelta(days=7, hours=1)) == "expiring"
    assert store.todo_state(job, T0 + timedelta(days=10)) == "expired"


def test_expired_todo_is_not_swept():
    job = add_todo(expires=T0 + timedelta(days=1))
    later = T0 + timedelta(days=2)
    store.sweep(later)
    assert job.path.exists()
    assert store.due_jobs(later) == []


def test_removing_an_expired_todo_uses_cancel():
    job = add_todo(expires=T0 + timedelta(days=1))
    store.cancel(job.id, "user confirmed", at=T0 + timedelta(days=2))
    assert (paths.done_dir() / f"{job.id}.yaml").exists()


def test_edit_extends_a_todo():
    job = add_todo(expires=T0 + timedelta(days=1))
    store.edit(job.id, expires=T0 + timedelta(days=30), when=T0)
    assert store.find(job.id).expires == T0 + timedelta(days=30)


def test_todo_cannot_be_snoozed_or_given_a_due_time():
    job = add_todo()
    with pytest.raises(JcronError, match="no due time"):
        store.snooze(job.id, T0 + timedelta(hours=1), at=T0)
    with pytest.raises(JcronError, match="no due time"):
        store.edit(job.id, at=T0 + timedelta(hours=1), when=T0)


def test_report_lists_up_to_three():
    jobs = [add_todo(f"todo {n}") for n in range(3)]
    report = display.todo_report(store.todos(None, T0), T0)
    assert all(j.id in report for j in jobs)
    assert "more TODO" not in report


def test_report_collapses_more_than_three_but_keeps_warnings():
    expiring = add_todo("soon", expires=T0 + timedelta(days=2))
    expired = add_todo("gone", expires=T0 - timedelta(hours=1))
    quiet = [add_todo(f"todo {n}") for n in range(2)]
    report = display.todo_report(store.todos(None, T0), T0)
    assert expiring.id in report and "Warn the user" in report
    assert expired.id in report and "remove it (cancel)" in report
    assert not any(j.id in report for j in quiet)
    assert "2 more TODO(s)" in report


def test_report_handles_a_todo_with_no_expiry():
    job = add_todo()
    job.expires = None
    store._save(job)
    report = display.todo_report(store.todos(None, T0), T0)
    assert job.id in report and "never expires" in report
    assert job.id in display.table(store.todos(None, T0), T0)


def test_hook_shows_todos_at_session_start_only():
    folder = str(paths.home() / "proj")
    job = add_todo(folder=folder)
    assert job.id in hook.run(session_start(folder), T0)
    prompt = json.dumps({"session_id": "abc", "hook_event_name": "UserPromptSubmit", "cwd": folder})
    assert hook.run(prompt, T0) == ""


def test_hook_skips_todos_for_other_folders():
    add_todo(folder=str(paths.home() / "proj"))
    assert hook.run(session_start(str(paths.home() / "other")), T0) == ""
