"""Text shown to people and LLMs."""

from __future__ import annotations

from datetime import datetime

from .model import Job
from .store import is_abandoned, todo_state, where
from .timeparse import human


def state(job: Job, at: datetime) -> str:
    folder = where(job)
    if folder == "done":
        return job.status
    if folder == "claimed":
        return "abandoned" if is_abandoned(job, at) else "claimed"
    if job.kind == "todo":
        return todo_state(job, at)
    if job.due is not None and job.due <= at:
        return "check due" if job.kind == "check" and job.condition_met is None else "due"
    return "waiting"


def reason(job: Job, at: datetime) -> str:
    """One phrase saying what a due job needs."""
    if where(job) == "claimed":
        return f"claimed by {job.claimed_by}, which looks abandoned"
    if job.kind == "check" and job.condition_met is None:
        return f"test the condition: {job.condition}"
    if job.kind == "check":
        return "condition met, do the action in the notes"
    return f"due {human(job.due, at)}" if job.due else "due"


def place(job: Job) -> str:
    text = f"folder: {job.folder}" if job.folder else "global"
    return f"{text}, branch: {job.branch}" if job.branch else text


def _when(job: Job, at: datetime) -> str:
    if where(job) == "done" and job.finished:
        return human(job.finished, at)
    if job.kind == "todo" and job.expires:
        return f"expires {human(job.expires, at)}"
    return human(job.due, at) if job.due else "-"


def line(job: Job, at: datetime) -> str:
    when = _when(job, at)
    return f"{job.id}  [{state(job, at)}] {job.kind}  {when}  {job.title}"


def table(jobs: list[Job], at: datetime) -> str:
    return "\n".join(line(j, at) for j in jobs) if jobs else "No jobs."


def full(job: Job, at: datetime) -> str:
    return f"# {job.id} [{state(job, at)}] {job.path}\n{job.to_yaml()}"


def due_report(jobs: list[Job], at: datetime) -> str:
    if not jobs:
        return "No jobs need attention."
    lines = [f"jcron: {len(jobs)} job(s) need attention. Tell the user what is due and ask before claiming any job."]
    for job in jobs:
        lines.append(f"- {job.id} [{job.kind}] {job.title} ({place(job)}): {reason(job, at)}")
    return "\n".join(lines)


TODO_LIST_LIMIT = 3


def todo_report(todos: list[Job], at: datetime) -> str:
    """The TODOs shown at session start: all of them when there are few, otherwise only the ones near or past expiry."""
    if not todos:
        return ""
    lines = [f"jcron: {len(todos)} TODO(s) for this folder or global. Tell the user about them, and ask before claiming any."]
    rest = []
    for job in todos:
        state = todo_state(job, at)
        if state == "expired":
            lines.append(f"- {job.id} {job.title} ({place(job)}): expired {human(job.expires, at)}. Ask the user whether to remove it (cancel) or extend it (edit expires).")
        elif state == "expiring":
            lines.append(f"- {job.id} {job.title} ({place(job)}): expires {human(job.expires, at)}. Warn the user, and offer to extend it.")
        else:
            rest.append(job)
    if len(todos) <= TODO_LIST_LIMIT:
        # A hand-edited TODO may have lost its expiry, so it never expires.
        lines += [f"- {job.id} {job.title} ({place(job)}): " + (f"expires {human(job.expires, at)}" if job.expires else "never expires") for job in rest]
    elif rest:
        lines.append(f"- {len(rest)} more TODO(s). Ask the user whether to show them, then call `todos`.")
    return "\n".join(lines)
