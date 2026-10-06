"""The jcron command line."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import display, store
from .model import KINDS
from .store import JcronError
from .timeparse import now, parse_when


def _session(args) -> str:
    return args.session or os.environ.get("JCRON_SESSION") or f"cli-{os.getppid()}"


def _notes(args) -> str | None:
    if getattr(args, "notes_file", None):
        if args.notes_file == "-":
            return sys.stdin.read()
        return Path(args.notes_file).read_text(encoding="utf-8")
    return args.notes


def _when(text: str | None):
    return parse_when(text) if text else None


def cmd_add(args) -> None:
    folder, branch = store.detect_folder_branch(args.folder, args.branch)
    job = store.add(
        args.kind,
        args.title,
        at=_when(args.at),
        cron=args.cron,
        condition=args.condition,
        every=args.every,
        expires=_when(args.expires),
        notes=_notes(args) or "",
        folder=folder,
        branch=branch,
        global_todo=args.global_todo,
    )
    print(f"Added {display.line(job, now())}")


def cmd_list(args) -> None:
    errors: list[str] = []
    at = now()
    jobs = store.list_jobs(include_done=args.all, errors=errors, at=at)
    if args.folder:
        wanted = str(Path(args.folder).resolve()).lower()
        jobs = [j for j in jobs if (j.folder or "").lower() == wanted]
    print(display.table(jobs, at))
    for error in errors:
        print(f"warning: could not read {error}", file=sys.stderr)


def cmd_show(args) -> None:
    print(display.full(store.find(args.id, include_done=True), now()), end="")


def cmd_due(args) -> None:
    if args.hook:
        from . import hook

        stdin_text = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")
        output = hook.respond(stdin_text)
        if output:
            print(output)
        return
    at = now()
    print(display.due_report(store.due_jobs(at), at))
    todo_text = display.todo_report(store.todos(os.getcwd(), at), at)
    if todo_text:
        print(f"\n{todo_text}")


def cmd_todos(args) -> None:
    at = now()
    found = store.todos(None if args.all else args.folder or os.getcwd(), at)
    print(display.table(found, at) if found else "No TODOs.")


def cmd_claim(args) -> None:
    job = store.claim(args.id, _session(args))
    print(f"Claimed {job.id} as {job.claimed_by}.\n")
    print(display.full(job, now()), end="")


def cmd_release(args) -> None:
    job = store.release(args.id, _notes(args))
    print(f"Released {display.line(job, now())}")


def cmd_done(args) -> None:
    job = store.done(args.id, _notes(args))
    if job.kind == "repeat":
        print(f"Done. Next run: {display.line(job, now())}")
    else:
        print(f"Done: {job.id}")


def cmd_check(args) -> None:
    job = store.check(args.id, args.met, _notes(args))
    at = now()
    if args.met:
        print(f"Condition met. {job.id} is now due as a task; do what its notes say, then run `jcron done {job.id}`.")
    else:
        print(f"Not yet. Next check: {display.line(job, at)}")


def cmd_snooze(args) -> None:
    job = store.snooze(args.id, parse_when(args.until), _notes(args))
    print(f"Snoozed {display.line(job, now())}")


def cmd_cancel(args) -> None:
    job = store.cancel(args.id, _notes(args))
    print(f"Cancelled {job.id}")


def cmd_edit(args) -> None:
    job = store.edit(
        args.id,
        title=args.title,
        notes=_notes(args),
        append_notes=args.append,
        at=_when(args.at),
        cron=args.cron,
        condition=args.condition,
        every=args.every,
        expires=_when(args.expires),
        folder=args.folder,
        branch=args.branch,
    )
    print(f"Updated {display.line(job, now())}")


def cmd_mcp(args) -> None:
    from .mcp_server import serve

    serve()


def cmd_install_hook(args) -> None:
    from . import hook

    def confirm(prompt: str) -> bool:
        print(prompt)
        return args.yes or input("Write this change? [y/N] ").strip().lower() in ("y", "yes")

    print(hook.install(Path(args.settings).expanduser(), args.command, confirm))


def _add_notes_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--notes", help="free text notes")
    group.add_argument("--notes-file", help="read notes from a file, or - for stdin")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jcron", description="Reminders, repeating tasks and condition checks for LLM sessions.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="add a job")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("title")
    p.add_argument("--at", help="when it is due: 'in 2h', 'tomorrow 9am' or an ISO time (check jobs: first check)")
    p.add_argument("--cron", help="repeat jobs: cron rule, for example '0 9 * * 1-5'")
    p.add_argument("--condition", help="check jobs: what has to be true, in plain words")
    p.add_argument("--every", help="check jobs: how often to check, for example 30m or 2h")
    p.add_argument("--expires", help="check jobs: when to give up; TODOs: when to expire (default: in 30 days)")
    p.add_argument("--folder", help="project folder (default: current directory)")
    p.add_argument("--branch", help="git branch (default: current branch, if any)")
    p.add_argument("--global", dest="global_todo", action="store_true", help="TODOs: show in every folder")
    _add_notes_options(p)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="list jobs")
    p.add_argument("--all", action="store_true", help="include finished, cancelled and expired jobs")
    p.add_argument("--folder", help="only jobs for this folder")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="print one job in full")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("due", help="list jobs that need attention")
    p.add_argument("--hook", action="store_true", help="Claude Code hook mode: read the event from stdin, print only new due jobs")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("todos", help="list TODOs for this folder plus global ones")
    p.add_argument("--folder", help="folder to list TODOs for (default: current directory)")
    p.add_argument("--all", action="store_true", help="list every TODO")
    p.set_defaults(func=cmd_todos)

    for name, func, text in (
        ("claim", cmd_claim, "claim a job so no other session takes it"),
        ("release", cmd_release, "give a claimed job back without finishing it"),
        ("done", cmd_done, "finish a job (repeat jobs move to their next run)"),
        ("cancel", cmd_cancel, "cancel a job"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("id")
        if name == "claim":
            p.add_argument("--session", help="who is claiming (default: $JCRON_SESSION or the parent process id)")
        else:
            _add_notes_options(p)
        p.set_defaults(func=func)

    p = sub.add_parser("check", help="report the result of a check job")
    p.add_argument("id")
    result = p.add_mutually_exclusive_group(required=True)
    result.add_argument("--met", dest="met", action="store_true", help="the condition is true")
    result.add_argument("--not-yet", dest="met", action="store_false", help="not yet; check again after the interval")
    _add_notes_options(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("snooze", help="move a job's due time later")
    p.add_argument("id")
    p.add_argument("--until", required=True, help="'in 1h', 'tomorrow 9am' or an ISO time")
    _add_notes_options(p)
    p.set_defaults(func=cmd_snooze)

    p = sub.add_parser("edit", help="change fields on a job")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--append", help="add a dated line to the notes")
    p.add_argument("--at", help="new due time")
    p.add_argument("--cron")
    p.add_argument("--condition")
    p.add_argument("--every")
    p.add_argument("--expires")
    p.add_argument("--folder")
    p.add_argument("--branch", help="new branch, or '' to clear it")
    _add_notes_options(p)
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("mcp", help="run the MCP server over stdio")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("install-hook", help="add the due-jobs hook to Claude Code settings")
    p.add_argument("--settings", default="~/.claude/settings.json")
    p.add_argument("--command", default="jcron due --hook", help="command the hook runs")
    p.add_argument("--yes", action="store_true", help="do not ask before writing")
    p.set_defaults(func=cmd_install_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (JcronError, ValueError, OSError) as e:
        print(f"jcron: {e}", file=sys.stderr)
        # The hook must never block a prompt, so it always exits cleanly.
        return 0 if getattr(args, "hook", False) else 1
    return 0
