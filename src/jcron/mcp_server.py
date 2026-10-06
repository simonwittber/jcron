"""The jcron MCP server: the command line actions as tools, plus instructions for the LLM."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import display, store
from .store import JcronError
from .timeparse import now, parse_when

INSTRUCTIONS = """\
jcron stores reminders, repeating tasks and condition checks that carry work from one session to a later one.
Jobs are YAML files in ~/.jcron/, and every session sees every job.

When to look:
- Call `due` at the start of a session.
- Call `due` again whenever a message starting with "jcron:" appears, listing jobs that need attention.

Working on a due job:
- Each job records a folder and, optionally, a git branch.
- Act on a job only when it belongs to the current work (same folder, and same branch if one is set).
- For due jobs that belong elsewhere, tell the user about them briefly and leave them alone.
- Never claim a job on your own. Tell the user what is due (use `show` to read the notes) and ask whether to take it on now.
- Only when the user says yes, call `claim`, so no other session takes the same job.
- If the user says not now, offer to `snooze` it. Otherwise leave it for another session.
- When finished, call `done` with a short note on the outcome. For a repeat job this schedules the next run.
- If you cannot finish, call `release` (or `snooze` to a later time) with a note on what you learned.

Check jobs:
- A check job has a plain-text condition, such as "PR 42 on jcron is merged".
- When one is due, test the condition with your own tools (gh, a Jira MCP, a web page, and so on).
- Then call `check` with met=true or met=false. met=false schedules the next check.
- Testing a condition needs no claim and no confirmation.
- met=true turns the job into a due task. Ask the user before claiming it and doing what its notes say, then call `done`.
- If you have no way to test the condition, tell the user rather than guessing.

Scheduling new jobs:
- Add a job when the user asks to be reminded, wants something done later or on a schedule, or work has to wait for something outside the session (a review, a ticket, a build).
- Write notes that a fresh session with no memory of this conversation can act on: what to do, why, the files, links and commands involved.
- Pass `folder` as your current working directory.
- Times accept relative phrases ("in 2h", "tomorrow 9am") or ISO times, and are stored in local time.
"""

mcp = MCPServer("jcron", instructions=INSTRUCTIONS)

# Each Claude Code session starts its own MCP server process, so the process id identifies the session.
SESSION = f"mcp-{os.getpid()}"


def tool(name: str | None = None):
    """Register a tool, passing expected errors (bad id, bad time) back to the LLM as readable messages."""

    def register(func):
        @functools.wraps(func)
        def run(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (JcronError, ValueError, OSError) as e:
                raise ToolError(str(e)) from e

        return mcp.tool(name=name)(run)

    return register


def _when(text: str | None):
    return parse_when(text) if text else None


@tool()
def add(
    kind: Literal["reminder", "repeat", "check"],
    title: str,
    notes: str = "",
    at: str | None = None,
    cron: str | None = None,
    condition: str | None = None,
    every: str | None = None,
    expires: str | None = None,
    folder: str | None = None,
    branch: str | None = None,
) -> str:
    """Schedule a job for a later session.

    kind: "reminder" (due once at `at`), "repeat" (due on the `cron` rule, e.g. "0 9 * * 1-5"),
    or "check" (test the plain-text `condition` every `every`, e.g. "30m"; optional `expires`).
    notes: everything a fresh session needs to act; for check jobs, what to do once the condition is met.
    at: "in 2h", "tomorrow 9am" or an ISO time. For check jobs it sets the first check (default: now + every).
    folder: your current working directory. branch: defaults to the folder's current git branch.
    """
    folder, branch = store.detect_folder_branch(folder, branch)
    job = store.add(
        kind, title, at=_when(at), cron=cron, condition=condition, every=every,
        expires=_when(expires), notes=notes, folder=folder, branch=branch,
    )
    return f"Added: {display.line(job, now())}"


@tool(name="list")
def list_jobs(include_done: bool = False, folder: str | None = None) -> str:
    """List jobs with their state and due time. include_done adds finished, cancelled and expired jobs."""
    at = now()
    jobs = store.list_jobs(include_done=include_done, at=at)
    if folder:
        wanted = str(Path(folder).resolve()).lower()
        jobs = [j for j in jobs if (j.folder or "").lower() == wanted]
    return display.table(jobs, at)


@tool()
def show(id: str) -> str:
    """Show one job in full, including its notes."""
    return display.full(store.find(id, include_done=True), now())


@tool()
def due() -> str:
    """List jobs that need attention now: due reminders and repeats, check jobs ready to test, and abandoned claims."""
    at = now()
    return display.due_report(store.due_jobs(at), at)


@tool()
def claim(id: str) -> str:
    """Claim a job so no other session takes it. Only call this after the user has agreed to work on the job now. Returns the full job."""
    job = store.claim(id, SESSION)
    return f"Claimed by {SESSION}.\n" + display.full(job, now())


@tool()
def release(id: str, notes: str | None = None) -> str:
    """Give a claimed job back without finishing it. Use notes to record what you learned."""
    job = store.release(id, notes)
    return f"Released: {display.line(job, now())}"


@tool()
def done(id: str, notes: str | None = None) -> str:
    """Finish a job, with a short note on the outcome. A repeat job moves to its next run instead."""
    job = store.done(id, notes)
    if job.kind == "repeat":
        return f"Done. Next run: {display.line(job, now())}"
    return f"Done: {job.id}"


@tool()
def check(id: str, met: bool, notes: str | None = None) -> str:
    """Report the result of testing a check job's condition.

    met=false schedules the next check after the job's interval.
    met=true makes the job a due task: do what its notes say, then call `done`.
    """
    job = store.check(id, met, notes)
    if met:
        return f"Condition met. {job.id} is now due as a task; do what its notes say, then call done."
    return f"Not yet. Next check: {display.line(job, now())}"


@tool()
def snooze(id: str, until: str, notes: str | None = None) -> str:
    """Move a job's due time later. until: "in 1h", "tomorrow 9am" or an ISO time."""
    job = store.snooze(id, parse_when(until), notes)
    return f"Snoozed: {display.line(job, now())}"


@tool()
def cancel(id: str, notes: str | None = None) -> str:
    """Cancel a job that is no longer needed."""
    job = store.cancel(id, notes)
    return f"Cancelled: {job.id}"


@tool()
def edit(
    id: str,
    title: str | None = None,
    notes: str | None = None,
    append_notes: str | None = None,
    at: str | None = None,
    cron: str | None = None,
    condition: str | None = None,
    every: str | None = None,
    expires: str | None = None,
    folder: str | None = None,
    branch: str | None = None,
) -> str:
    """Change fields on a job. notes replaces the notes; append_notes adds a dated line. at sets a new due time."""
    job = store.edit(
        id, title=title, notes=notes, append_notes=append_notes, at=_when(at), cron=cron,
        condition=condition, every=every, expires=_when(expires), folder=folder, branch=branch,
    )
    return f"Updated: {display.line(job, now())}"


def serve() -> None:
    mcp.run()
