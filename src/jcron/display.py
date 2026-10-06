"""Text shown to people and LLMs."""

from __future__ import annotations

from datetime import datetime

from .model import Job
from .store import is_abandoned, where
from .timeparse import human


def state(job: Job, at: datetime) -> str:
    folder = where(job)
    if folder == "done":
        return job.status
    if folder == "claimed":
        return "abandoned" if is_abandoned(job, at) else "claimed"
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
    text = f"folder: {job.folder}" if job.folder else "no folder"
    return f"{text}, branch: {job.branch}" if job.branch else text


def line(job: Job, at: datetime) -> str:
    when = human(job.finished, at) if where(job) == "done" and job.finished else human(job.due, at) if job.due else "-"
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
