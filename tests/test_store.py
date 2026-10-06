from datetime import datetime, timedelta

import pytest

from jcron import paths, store
from jcron.model import Job
from jcron.store import JcronError
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


def add_reminder(title="Look at CI", due=T0 + timedelta(hours=1), **kw):
    return store.add("reminder", title, at=due, base=T0, folder="C:/work/proj", branch="main", **kw)


def test_add_writes_readable_yaml():
    job = add_reminder(notes="line one\nline two")
    text = job.path.read_text(encoding="utf-8")
    assert job.path.parent == paths.jobs_dir()
    assert "due: 2026-10-06T13:00:00" in text
    assert "notes: |" in text
    loaded = Job.from_yaml(text, job.path)
    assert loaded.due == job.due
    assert loaded.notes == "line one\nline two\n"
    assert loaded.branch == "main"
    assert "add" in paths.log_file().read_text(encoding="utf-8")


def test_unknown_keys_survive_a_save():
    job = add_reminder()
    job.path.write_text(job.path.read_text(encoding="utf-8") + "priority: high\n", encoding="utf-8")
    store.edit(job.id, title="New title", when=T0)
    assert "priority: high" in store.find(job.id).path.read_text(encoding="utf-8")


def test_find_by_prefix():
    job = add_reminder(title="unique thing")
    assert store.find("unique").id == job.id
    with pytest.raises(JcronError):
        store.find("nothing-like-this")


def test_due_only_lists_jobs_whose_time_has_come():
    early = add_reminder(title="early", due=T0 + timedelta(minutes=10))
    add_reminder(title="late", due=T0 + timedelta(hours=5))
    assert [j.id for j in store.due_jobs(T0 + timedelta(hours=1))] == [early.id]


def test_claim_moves_file_and_blocks_other_sessions():
    job = add_reminder()
    claimed = store.claim(job.id, "session-a", at=T0)
    assert claimed.path.parent == paths.claimed_dir()
    assert not (paths.jobs_dir() / f"{job.id}.yaml").exists()
    with pytest.raises(JcronError, match="already claimed"):
        store.claim(job.id, "session-b", at=T0 + timedelta(minutes=5))
    # The same session may claim again.
    store.claim(job.id, "session-a", at=T0 + timedelta(minutes=5))


def test_abandoned_claim_is_due_again_and_can_be_taken_over():
    job = add_reminder(due=T0)
    store.claim(job.id, "session-a", at=T0)
    later = T0 + store.CLAIM_TIMEOUT + timedelta(minutes=1)
    assert [j.id for j in store.due_jobs(later)] == [job.id]
    taken = store.claim(job.id, "session-b", at=later)
    assert taken.claimed_by == "session-b"
    assert "took_over=session-a" in paths.log_file().read_text(encoding="utf-8")


def test_claim_race_only_one_wins(monkeypatch):
    job = add_reminder()
    stale = store.find(job.id)
    store.claim(job.id, "session-a", at=T0)
    # A second session that looked the job up before the first claim landed must lose the rename.
    monkeypatch.setattr(store, "find", lambda *a, **k: stale)
    with pytest.raises(JcronError, match="just claimed"):
        store.claim(job.id, "session-b", at=T0)


def test_release_puts_job_back():
    job = add_reminder()
    store.claim(job.id, "s", at=T0)
    released = store.release(job.id, "ran out of time", at=T0)
    assert released.path.parent == paths.jobs_dir()
    assert released.claimed_by is None
    assert "ran out of time" in released.notes


def test_done_reminder_moves_to_done():
    job = add_reminder()
    store.claim(job.id, "s", at=T0)
    finished = store.done(job.id, "all green", at=T0)
    assert finished.path.parent == paths.done_dir()
    assert finished.status == "done"
    assert not list(paths.claimed_dir().glob("*.yaml"))


def test_repeat_job_moves_to_next_run():
    job = store.add("repeat", "standup notes", cron="0 9 * * *", base=T0)
    assert (job.due.day, job.due.hour) == (7, 9)
    store.claim(job.id, "s", at=job.due)
    after = store.done(job.id, at=job.due + timedelta(minutes=20))
    assert (after.due.day, after.due.hour) == (8, 9)
    assert after.path.parent == paths.jobs_dir()
    assert after.claimed_by is None


def test_repeat_done_early_skips_current_run():
    job = store.add("repeat", "weekly", cron="0 9 * * *", base=T0)
    after = store.done(job.id, at=T0)
    assert (after.due.day, after.due.hour) == (8, 9)


def test_bad_cron_rule():
    with pytest.raises(ValueError):
        store.add("repeat", "x", cron="whenever", base=T0)


def test_check_job_flow():
    job = store.add("check", "delete branch", condition="PR 42 merged", every="30m", base=T0)
    assert job.due == T0 + timedelta(minutes=30)
    store.claim(job.id, "s", at=job.due)
    not_yet = store.check(job.id, False, "still open", at=job.due)
    assert not_yet.due == job.due + timedelta(minutes=30)
    assert not_yet.path.parent == paths.jobs_dir()
    met = store.check(job.id, True, at=not_yet.due)
    assert met.condition_met == not_yet.due
    assert [j.id for j in store.due_jobs(not_yet.due)] == [job.id]
    assert store.done(job.id, at=not_yet.due).status == "done"


def test_check_job_expires():
    job = store.add("check", "wait", condition="ticket resolved", every="1h", expires=T0 + timedelta(hours=2), base=T0)
    assert store.due_jobs(T0 + timedelta(hours=3)) == []
    expired = store.find(job.id, include_done=True)
    assert expired.status == "expired"
    assert expired.path.parent == paths.done_dir()


def test_check_on_non_check_job_fails():
    job = add_reminder()
    with pytest.raises(JcronError):
        store.check(job.id, True, at=T0)


def test_snooze_and_cancel():
    job = add_reminder(due=T0)
    snoozed = store.snooze(job.id, T0 + timedelta(days=1), at=T0)
    assert snoozed.due == T0 + timedelta(days=1)
    assert store.cancel(job.id, at=T0).path.parent == paths.done_dir()


def test_broken_file_does_not_hide_other_jobs():
    job = add_reminder()
    (paths.jobs_dir() / "broken.yaml").write_text("::: not yaml [", encoding="utf-8")
    errors = []
    assert [j.id for j in store.list_jobs(errors=errors, at=T0)] == [job.id]
    assert errors


def test_add_never_reuses_a_taken_id(monkeypatch):
    first = add_reminder()
    ids = iter([first.id, first.id, "look-at-ci-beef"])
    monkeypatch.setattr(store, "make_id", lambda title: next(ids))
    second = add_reminder()
    assert second.id == "look-at-ci-beef"
    assert first.path.exists()


def test_move_leaves_one_copy():
    job = add_reminder()
    old = job.path
    store.done(job.id)
    assert not old.exists()
    assert (paths.done_dir() / f"{job.id}.yaml").exists()
