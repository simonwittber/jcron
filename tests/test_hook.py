import json
from datetime import datetime, timedelta

from jcron import hook, store
from jcron.timeparse import to_local

T0 = to_local(datetime(2026, 10, 6, 12, 0, 0))


def event(name="UserPromptSubmit", session="abc-123"):
    return json.dumps({"session_id": session, "hook_event_name": name})


def test_nothing_due_prints_nothing():
    store.add("reminder", "later", at=T0 + timedelta(hours=1), base=T0)
    assert hook.run(event(), T0) == ""


def test_due_job_is_reported_once_per_session():
    job = store.add("reminder", "look at CI", at=T0, base=T0, folder="C:/proj", branch="main")
    first = hook.run(event(), T0)
    assert job.id in first and "branch: main" in first
    assert hook.run(event(), T0 + timedelta(minutes=1)) == ""
    assert job.id in hook.run(event(session="other"), T0)


def test_session_start_repeats_everything():
    job = store.add("reminder", "look at CI", at=T0, base=T0)
    hook.run(event(), T0)
    assert job.id in hook.run(event("SessionStart"), T0)


def test_next_check_is_reported_again():
    job = store.add("check", "wait for PR", condition="PR merged", every="30m", base=T0)
    assert "test the condition: PR merged" in hook.run(event(), job.due)
    store.check(job.id, False, at=job.due)
    later = job.due + timedelta(minutes=30)
    assert job.id in hook.run(event(), later)


def test_no_stdin_reports_every_time():
    store.add("reminder", "x", at=T0, base=T0)
    assert hook.run("", T0)
    assert hook.run("", T0)


def test_install_adds_hooks_once(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    message = hook.install(settings, "jcron due --hook", lambda _: True)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["model"] == "opus"
    assert set(data["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    assert "Installed" in message
    assert "already installed" in hook.install(settings, "jcron due --hook", lambda _: True)
    assert (tmp_path / "settings.json.bak").exists()


def test_install_declined_changes_nothing(tmp_path):
    settings = tmp_path / "settings.json"
    assert hook.install(settings, "jcron due --hook", lambda _: False) == "Nothing changed."
    assert not settings.exists()
