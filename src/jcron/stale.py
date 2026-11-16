"""The weekly report of jobs that look stale, so the user can decide what to do with them."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import paths, store
from .display import place
from .model import Job
from .timeparse import fmt, human, now, to_local

REPORT_EVERY = timedelta(days=7)
OVERDUE_LIMIT = timedelta(days=14)


def reasons(job: Job, at: datetime) -> list[str]:
    """Why a job looks stale; empty when it does not."""
    found = []
    folder_gone = job.folder is not None and not Path(job.folder).exists()
    if folder_gone:
        found.append("its folder is gone")
    if job.branch and job.folder is not None and not _branch_exists(job, folder_gone):
        found.append(f"branch {job.branch} is gone")
    if store.where(job) == "claimed":
        if job.claimed_at is not None and at - job.claimed_at > OVERDUE_LIMIT:
            found.append(f"claimed {human(job.claimed_at, at)} and never finished")
    elif job.due is not None and at - job.due > OVERDUE_LIMIT:
        found.append(f"overdue since {human(job.due, at)}")
    if job.kind == "todo" and store.todo_state(job, at) == "expired":
        found.append(f"expired {human(job.expires, at)}")
    return found


def _branch_exists(job: Job, folder_gone: bool) -> bool:
    """Whether the branch is still there locally or as a remote-tracking ref. No network.
    When git cannot be asked at all, count the branch as present, so the job is not wrongly reported."""
    where = job.repo if folder_gone else job.folder
    if where is None or not Path(where).exists():
        return True
    try:
        result = subprocess.run(
            ["git", "-C", where, "for-each-ref", "--format=%(refname)", f"refs/heads/{job.branch}", f"refs/remotes/*/{job.branch}"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode != 0 or bool(result.stdout.strip())


def stale_jobs(at: datetime | None = None) -> list[tuple[Job, list[str]]]:
    at = at or now()
    found = []
    for job in store.list_jobs(at=at):
        why = reasons(job, at)
        if why:
            found.append((job, why))
    return found


def weekly(at: datetime | None = None) -> list[tuple[Job, list[str]]]:
    """The stale jobs, when a week has passed since the last report; otherwise an empty list."""
    at = at or now()
    marker = paths.home() / "last-stale-report.txt"
    try:
        last = to_local(datetime.fromisoformat(marker.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        last = None
    if last is not None and at - last < REPORT_EVERY:
        return []
    # Write the time before reporting, so sessions starting together do not all report.
    # A report the user ignores still counts, so it waits another week.
    paths.ensure()
    marker.write_text(fmt(at) + "\n", encoding="utf-8")
    return stale_jobs(at)


def report(found: list[tuple[Job, list[str]]]) -> str:
    if not found:
        return ""
    lines = [
        f"jcron: weekly cleanup. {len(found)} job(s) across all folders look stale. "
        "List them for the user and ask about each one: cancel it, edit it, or keep it. Change nothing without an answer, and do not work on them here."
    ]
    for job, why in found:
        lines.append(f"- {job.id} [{job.kind}] {job.title} ({place(job)}): {'; '.join(why)}")
    return "\n".join(lines)
