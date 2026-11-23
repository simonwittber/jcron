import json
import subprocess
from datetime import datetime, timedelta

import pytest

from jcron import display, hook, store
from jcron.store import JcronError
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo with a subfolder and a second branch in a worktree, plus a plain folder outside git."""
    main = tmp_path / "proj"
    (main / "src").mkdir(parents=True)
    git(main, "init", "-b", "main")
    git(main, "commit", "--allow-empty", "-m", "start")
    git(main, "worktree", "add", "-b", "feature", str(tmp_path / "proj-wt"))
    (tmp_path / "plain").mkdir()
    monkeypatch.chdir(main)
    return tmp_path


def add_shared(repo, title="Promote the build", **kw):
    kw.setdefault("at", T0)
    return store.add("reminder", title, base=T0, folder=str(repo / "proj"), branch="main", shared=True, **kw)


def ids(jobs):
    return [j.id for j in jobs]


def test_shared_job_is_saved_in_the_repo_without_machine_paths(repo):
    job = add_shared(repo)
    assert job.path == repo / "proj" / ".jcron" / f"{job.id}.yaml"
    assert job.folder is None and job.repo is None
    assert job.branch == "main"
    assert not list((store.paths.jobs_dir()).glob("*.yaml"))


def test_shared_job_needs_a_git_repo(repo):
    with pytest.raises(JcronError, match="needs a git repo"):
        store.add("reminder", "x", at=T0, base=T0, folder=str(repo / "plain"), shared=True)


def test_shared_job_cannot_be_global(repo):
    with pytest.raises(JcronError, match="cannot be global"):
        store.add("todo", "x", base=T0, folder=str(repo / "proj"), shared=True, global_todo=True)


def test_shared_job_is_due_in_its_checkout_only(repo):
    job = add_shared(repo)
    assert ids(store.due_jobs(T0, str(repo / "proj" / "src"))) == [job.id]
    assert store.due_jobs(T0, str(repo / "plain")) == []
    # The worktree is another checkout of the repo, and does not have the file until the branch brings it.
    assert store.due_jobs(T0, str(repo / "proj-wt")) == []


def test_shared_job_is_not_due_before_its_time(repo):
    add_shared(repo, at=T0 + timedelta(days=1))
    assert store.due_jobs(T0, str(repo / "proj")) == []


def test_claim_changes_nothing_for_a_shared_job(repo):
    job = add_shared(repo)
    before = job.path.read_text(encoding="utf-8")
    claimed = store.claim(job.id, "session-1", T0)
    assert claimed.claimed_by is None
    assert job.path.read_text(encoding="utf-8") == before


def test_done_keeps_the_file_and_marks_it_done(repo):
    job = add_shared(repo)
    store.done(job.id, "promoted", T0)
    assert job.path.exists()
    text = job.path.read_text(encoding="utf-8")
    assert "status: done" in text and "promoted" in text
    assert store.due_jobs(T0, str(repo / "proj")) == []
    assert not list(store.paths.done_dir().glob("*.yaml"))


def test_finished_shared_jobs_are_listed_for_deletion(repo):
    job = add_shared(repo)
    assert store.finished_shared(str(repo / "proj")) == []
    store.done(job.id, at=T0)
    assert ids(store.finished_shared(str(repo / "proj"))) == [job.id]
    assert store.finished_shared(str(repo / "plain")) == []
    assert job.id in display.finished_report(store.finished_shared(str(repo / "proj")))


def test_finished_shared_job_is_hidden_from_list_and_find_until_asked(repo):
    job = add_shared(repo)
    store.done(job.id, at=T0)
    assert store.list_jobs(at=T0) == []
    assert ids(store.list_jobs(include_done=True, at=T0)) == [job.id]
    with pytest.raises(JcronError, match="no job"):
        store.find(job.id)
    assert store.find(job.id, include_done=True).id == job.id
    assert "[done]" in display.line(store.find(job.id, include_done=True), T0)


def test_repeat_job_stays_in_the_repo_after_done(repo):
    job = store.add("repeat", "Weekly check", cron="0 9 * * 1", base=T0, folder=str(repo / "proj"), shared=True)
    done = store.done(job.id, at=job.due)
    assert done.path == job.path and done.status == "waiting"
    assert done.due > job.due


def test_cancel_and_snooze_work_in_place(repo):
    one = add_shared(repo, "one")
    two = add_shared(repo, "two")
    store.snooze(one.id, T0 + timedelta(days=2), at=T0)
    assert ids(store.due_jobs(T0, str(repo / "proj"))) == [two.id]
    store.cancel(two.id, at=T0)
    assert ids(store.finished_shared(str(repo / "proj"))) == [two.id]
    assert one.path.exists() and two.path.exists()


def test_shared_todos_are_listed_for_the_checkout(repo):
    job = store.add("todo", "Tidy up", base=T0, folder=str(repo / "proj"), shared=True)
    assert ids(store.todos(str(repo / "proj"), T0)) == [job.id]
    assert store.todos(str(repo / "plain"), T0) == []


def test_session_start_reports_finished_shared_jobs(repo):
    job = add_shared(repo)
    store.done(job.id, at=T0)
    event = json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": str(repo / "proj")})
    text = hook.run(event, T0)
    assert "finished shared job" in text and job.id in text
    other = json.dumps({"session_id": "t", "hook_event_name": "SessionStart", "cwd": str(repo / "plain")})
    assert hook.run(other, T0) == ""
