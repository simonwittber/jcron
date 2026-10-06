import asyncio

from jcron import paths
from jcron.cli import main


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def only_job_id():
    return next(paths.jobs_dir().glob("*.yaml")).stem


def test_cli_round_trip(capsys, tmp_path):
    code, out, _ = run(capsys, "add", "reminder", "Check the build", "--at", "now", "--notes", "see CI page", "--folder", str(tmp_path))
    assert code == 0 and "Added" in out
    job_id = only_job_id()
    assert job_id in run(capsys, "due")[1]
    assert "see CI page" in run(capsys, "show", job_id[:6])[1]
    assert "Claimed" in run(capsys, "claim", job_id, "--session", "me")[1]
    assert run(capsys, "done", job_id, "--notes", "green")[0] == 0
    assert "No jobs." in run(capsys, "list")[1]
    assert "[done]" in run(capsys, "list", "--all")[1]


def test_cli_errors_exit_nonzero(capsys):
    code, _, err = run(capsys, "add", "reminder", "No time given")
    assert code == 1 and "needs a time" in err
    assert run(capsys, "done", "missing")[0] == 1


def test_mcp_tools_round_trip(tmp_path):
    from jcron import mcp_server as m

    added = m.add("check", "Ship it", notes="merge and tag", condition="PR 7 approved", every="1h", at="now", folder=str(tmp_path))
    assert "Added" in added
    job_id = only_job_id()
    assert "test the condition: PR 7 approved" in m.due()
    assert "Claimed by mcp-" in m.claim(job_id)
    assert "Condition met" in m.check(job_id, True)
    assert "Done" in m.done(job_id, "tagged v1")
    assert m.list_jobs() == "No jobs."


def test_mcp_server_lists_tools_and_instructions():
    from jcron import mcp_server as m

    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert {"add", "list", "show", "due", "claim", "release", "done", "check", "snooze", "cancel", "edit", "todos"} <= names
    assert "At the start of a session, call `due`" in m.mcp.instructions


def test_mcp_todo_round_trip(tmp_path):
    from jcron import mcp_server as m

    assert "Added" in m.add("todo", "Tidy the README", notes="shorten the intro", folder=str(tmp_path))
    job_id = only_job_id()
    assert job_id in m.due(folder=str(tmp_path))
    assert job_id in m.todos(folder=str(tmp_path))
    assert m.todos(folder=str(tmp_path.parent)) == "No TODOs."
    assert "Done" in m.done(job_id)


def test_cli_global_todo(capsys, tmp_path):
    code, out, _ = run(capsys, "add", "todo", "Renew the cert", "--global", "--folder", str(tmp_path))
    assert code == 0 and "[todo]" in out
    assert "Renew the cert" in run(capsys, "todos", "--folder", str(tmp_path / "anywhere"))[1]
