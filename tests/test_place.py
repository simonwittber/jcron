import json
import subprocess
from datetime import datetime

import pytest

from jcron import hook, store
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repo with a subfolder, a second branch checked out in a worktree, and an unrelated repo next to it."""
    main = tmp_path / "proj"
    (main / "src" / "deep").mkdir(parents=True)
    git(main, "init", "-b", "main")
    git(main, "commit", "--allow-empty", "-m", "start")
    git(main, "worktree", "add", "-b", "feature", str(tmp_path / "proj-wt"))
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-b", "main")
    return tmp_path


def ids(jobs):
    return [j.id for j in jobs]


def test_job_shows_anywhere_in_its_repo(repo):
    job = store.add("reminder", "look at CI", at=T0, base=T0, folder=str(repo / "proj" / "src"), branch="main")
    assert job.repo is not None
    for folder in (repo / "proj", repo / "proj" / "src" / "deep", repo / "proj-wt"):
        assert ids(store.due_jobs(T0, str(folder))) == [job.id]


def test_job_stays_out_of_other_repos_and_folders(repo):
    store.add("reminder", "look at CI", at=T0, base=T0, folder=str(repo / "proj"), branch="main")
    assert store.due_jobs(T0, str(repo / "other")) == []
    assert store.due_jobs(T0, str(repo)) == []


def test_job_from_a_worktree_shows_in_the_main_checkout(repo):
    job = store.add("todo", "tidy up", base=T0, folder=str(repo / "proj-wt"), branch="feature")
    assert ids(store.todos(str(repo / "proj"), T0)) == [job.id]


def test_older_job_without_repo_is_still_matched(repo):
    job = store.add("reminder", "look at CI", at=T0, base=T0, folder=str(repo / "proj"))
    job.repo = None
    store._save(job)
    assert ids(store.due_jobs(T0, str(repo / "proj-wt"))) == [job.id]
    assert store.due_jobs(T0, str(repo / "other")) == []


def test_edit_folder_updates_repo(repo):
    job = store.add("reminder", "look at CI", at=T0, base=T0, folder=str(repo / "proj"))
    store.edit(job.id, folder=str(repo / "other"), when=T0)
    assert ids(store.due_jobs(T0, str(repo / "other"))) == [job.id]
    assert store.due_jobs(T0, str(repo / "proj")) == []


def test_hook_reports_only_this_repo(repo):
    mine = store.add("reminder", "mine", at=T0, base=T0, folder=str(repo / "proj"))
    theirs = store.add("reminder", "theirs", at=T0, base=T0, folder=str(repo / "other"))
    text = hook.run(json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": str(repo / "proj-wt")}), T0)
    assert mine.id in text and theirs.id not in text
