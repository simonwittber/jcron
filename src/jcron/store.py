"""Reading, writing and moving job files."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import paths, schedule
from .model import KINDS, Job, make_id
from .timeparse import fmt, now, parse_duration

CLAIM_TIMEOUT = timedelta(hours=4)
TODO_EXPIRY = timedelta(days=30)
TODO_WARNING = timedelta(days=3)


class JcronError(Exception):
    pass


# Files


def _read(path: Path) -> Job:
    return Job.from_yaml(path.read_text(encoding="utf-8"), path)


def _write(job: Job, path: Path) -> None:
    # Write a temporary file and swap it in, so readers never see a half-written job.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(job.to_yaml(), encoding="utf-8")
    os.replace(tmp, path)
    job.path = path


def _save(job: Job) -> None:
    _write(job, job.path)


def _move(job: Job, folder: Path) -> None:
    target = folder / f"{job.id}.yaml"
    old = job.path
    if old is None or old == target:
        _write(job, target)
        return
    # Save in place, then rename, so the job is never in two folders at once.
    _write(job, old)
    os.replace(old, target)
    job.path = target


def _load_dir(folder: Path, errors: list[str] | None = None) -> list[Job]:
    jobs = []
    for path in sorted(folder.glob("*.yaml")):
        try:
            jobs.append(_read(path))
        except Exception as e:  # A broken hand edit should not hide every other job.
            if errors is not None:
                errors.append(f"{path}: {e}")
    return jobs


def log(action: str, job: Job, detail: str = "", at: datetime | None = None) -> None:
    line = f"{fmt(at or now())} {action} {job.id} {json.dumps(job.title, ensure_ascii=False)}"
    if detail:
        line += f" {detail}"
    with paths.log_file().open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _append_note(job: Job, label: str, text: str | None, at: datetime) -> None:
    if not text:
        return
    entry = f"[{fmt(at)} {label}] {text.strip()}"
    job.notes = f"{job.notes.rstrip()}\n\n{entry}\n" if job.notes.strip() else f"{entry}\n"


def _clear_claim(job: Job) -> None:
    job.claimed_by = None
    job.claimed_at = None
    job.status = "waiting"


# Lookup


def where(job: Job) -> str:
    """Which folder the job is in: jobs, claimed or done."""
    return job.path.parent.name if job.path else "jobs"


def is_abandoned(job: Job, at: datetime) -> bool:
    return where(job) == "claimed" and (job.claimed_at is None or at - job.claimed_at >= CLAIM_TIMEOUT)


def todo_state(job: Job, at: datetime) -> str:
    """For a TODO: expired, expiring (within the warning window) or todo."""
    if job.expires is not None and job.expires <= at:
        return "expired"
    if job.expires is not None and job.expires - at <= TODO_WARNING:
        return "expiring"
    return "todo"


def find(job_id: str, include_done: bool = False) -> Job:
    """Find a job by its id or by a unique start of its id."""
    paths.ensure()
    folders = [paths.jobs_dir(), paths.claimed_dir()] + ([paths.done_dir()] if include_done else [])
    for folder in folders:
        exact = folder / f"{job_id}.yaml"
        if exact.exists():
            return _read(exact)
    matches = [p for folder in folders for p in folder.glob(f"{job_id}*.yaml")]
    if len(matches) == 1:
        return _read(matches[0])
    if not matches:
        raise JcronError(f"no job with id {job_id!r}")
    raise JcronError(f"{job_id!r} matches several jobs: {', '.join(p.stem for p in matches)}")


def list_jobs(include_done: bool = False, errors: list[str] | None = None, at: datetime | None = None) -> list[Job]:
    at = at or now()
    sweep(at)
    folders = [paths.jobs_dir(), paths.claimed_dir()] + ([paths.done_dir()] if include_done else [])
    jobs = [job for folder in folders for job in _load_dir(folder, errors)]
    return sorted(jobs, key=lambda j: (j.due is None, j.due or at))


def due_jobs(at: datetime | None = None) -> list[Job]:
    """Jobs whose time has come, plus claimed jobs whose session seems to have gone away."""
    at = at or now()
    sweep(at)
    ready = [j for j in _load_dir(paths.jobs_dir()) if j.due is not None and j.due <= at]
    abandoned = [j for j in _load_dir(paths.claimed_dir()) if is_abandoned(j, at)]
    return sorted(ready + abandoned, key=lambda j: j.due or at)


def todos(folder: str | None = None, at: datetime | None = None) -> list[Job]:
    """Waiting TODOs for a folder or any folder above it, plus global ones (all TODOs when no folder is given), soonest expiry first."""
    at = at or now()
    paths.ensure()
    wanted = _folder_parts(str(Path(folder).resolve())) if folder else None
    found = [
        j for j in _load_dir(paths.jobs_dir())
        if j.kind == "todo" and (wanted is None or j.folder is None or _is_within(wanted, _folder_parts(j.folder)))
    ]
    return sorted(found, key=lambda j: (j.expires is None, j.expires or at))


def _folder_parts(folder: str) -> list[str]:
    return [part.lower() for part in Path(folder).parts]


def _is_within(inner: list[str], outer: list[str]) -> bool:
    # Compare whole folder names, so "proj" never matches "proj-old".
    return inner[:len(outer)] == outer


def sweep(at: datetime | None = None) -> None:
    """Move check jobs past their expiry into done/.
    Expired TODOs stay, because only the user can confirm their removal."""
    at = at or now()
    paths.ensure()
    candidates = _load_dir(paths.jobs_dir()) + [j for j in _load_dir(paths.claimed_dir()) if is_abandoned(j, at)]
    for job in candidates:
        if job.kind == "check" and job.condition_met is None and job.expires is not None and job.expires <= at:
            _clear_claim(job)
            job.status = "expired"
            job.finished = at
            _move(job, paths.done_dir())
            log("expire", job, at=at)


def _new_id(title: str) -> str:
    # Pick again if the id is taken, so a new job never overwrites an old one.
    while True:
        job_id = make_id(title)
        if not any((folder / f"{job_id}.yaml").exists() for folder in (paths.jobs_dir(), paths.claimed_dir(), paths.done_dir())):
            return job_id


# Context


def detect_folder_branch(folder: str | None = None, branch: str | None = None) -> tuple[str, str | None]:
    """Fill in the folder (current directory) and git branch when they are not given."""
    folder = str(Path(folder or os.getcwd()).resolve())
    if branch is None:
        try:
            result = subprocess.run(
                ["git", "-C", folder, "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
            )
            branch = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            branch = None
    return folder, branch or None


# Actions


def add(
    kind: str,
    title: str,
    *,
    at: datetime | None = None,
    cron: str | None = None,
    condition: str | None = None,
    every: str | None = None,
    expires: datetime | None = None,
    notes: str = "",
    folder: str | None = None,
    branch: str | None = None,
    global_todo: bool = False,
    base: datetime | None = None,
) -> Job:
    if kind not in KINDS:
        raise JcronError(f"kind must be one of {', '.join(KINDS)}")
    if not title.strip():
        raise JcronError("a job needs a title")
    if global_todo and kind != "todo":
        raise JcronError("only TODOs can be global")
    base = base or now()
    paths.ensure()
    job = Job(id=_new_id(title), kind=kind, title=title.strip(), created=base, folder=folder, branch=branch, notes=notes)
    if kind == "reminder":
        if at is None:
            raise JcronError("a reminder needs a time (at)")
        job.due = at
    elif kind == "repeat":
        if not cron:
            raise JcronError("a repeat job needs a cron rule (cron)")
        schedule.validate_cron(cron)
        job.repeat = cron
        job.due = at or schedule.next_cron(cron, base)
    elif kind == "todo":
        if at is not None:
            raise JcronError("a TODO has no due time; set when it expires instead (expires)")
        job.expires = expires or base + TODO_EXPIRY
        if global_todo:
            job.folder = None
    else:
        if not condition or not every:
            raise JcronError("a check job needs a condition and a check interval (every)")
        interval = parse_duration(every)
        job.condition = condition
        job.check_every = every
        job.due = at or base + interval
        job.expires = expires
    if job.notes and not job.notes.endswith("\n"):
        job.notes += "\n"
    _write(job, paths.jobs_dir() / f"{job.id}.yaml")
    log("add", job, f"kind={kind} " + (f"expires={fmt(job.expires)}" if kind == "todo" else f"due={fmt(job.due)}"), at=base)
    return job


def claim(job_id: str, session: str, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    if where(job) == "claimed" and job.claimed_by != session and not is_abandoned(job, at):
        raise JcronError(f"{job.id} is already claimed by {job.claimed_by} since {fmt(job.claimed_at)}")

    # Renaming is a single step, so when two sessions race for the same file only one rename succeeds.
    grab = paths.claimed_dir() / f".{job.id}.{secrets.token_hex(4)}.grab"
    try:
        os.rename(job.path, grab)
    except FileNotFoundError:
        raise JcronError(f"{job.id} was just claimed by another session") from None
    job = _read(grab)
    taken_from = job.claimed_by if where(job) == "claimed" else None
    job.status = "claimed"
    job.claimed_by = session
    job.claimed_at = at
    _write(job, grab)
    target = paths.claimed_dir() / f"{job.id}.yaml"
    os.replace(grab, target)
    job.path = target
    log("claim", job, f"session={session}" + (f" took_over={taken_from}" if taken_from and taken_from != session else ""), at=at)
    return job


def release(job_id: str, notes: str | None = None, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    if where(job) != "claimed":
        raise JcronError(f"{job.id} is not claimed")
    _append_note(job, "released", notes, at)
    _clear_claim(job)
    _move(job, paths.jobs_dir())
    log("release", job, at=at)
    return job


def done(job_id: str, notes: str | None = None, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    _append_note(job, "done", notes, at)
    if job.kind == "repeat":
        # Finish the current occurrence, even when it is done early, then move to the one after.
        job.last_done = at
        job.due = schedule.next_cron(job.repeat, max(at, job.due or at))
        _clear_claim(job)
        _move(job, paths.jobs_dir())
        log("done", job, f"next={fmt(job.due)}", at=at)
    else:
        job.status = "done"
        job.finished = at
        _move(job, paths.done_dir())
        log("done", job, at=at)
    return job


def check(job_id: str, met: bool, notes: str | None = None, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    if job.kind != "check":
        raise JcronError(f"{job.id} is a {job.kind} job, not a check job")
    if met:
        _append_note(job, "condition met", notes, at)
        job.condition_met = at
        job.due = at
        _save(job)
        log("check", job, "met", at=at)
    else:
        _append_note(job, "not yet", notes, at)
        job.due = at + parse_duration(job.check_every or "1h")
        if where(job) == "claimed":
            _clear_claim(job)
            _move(job, paths.jobs_dir())
        else:
            _save(job)
        log("check", job, f"not-yet next={fmt(job.due)}", at=at)
    return job


def snooze(job_id: str, until: datetime, notes: str | None = None, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    if job.kind == "todo":
        raise JcronError("a TODO has no due time to snooze; extend it with edit (expires) instead")
    _append_note(job, "snoozed", notes, at)
    job.due = until
    if where(job) == "claimed":
        _clear_claim(job)
        _move(job, paths.jobs_dir())
    else:
        _save(job)
    log("snooze", job, f"until={fmt(until)}", at=at)
    return job


def cancel(job_id: str, notes: str | None = None, at: datetime | None = None) -> Job:
    at = at or now()
    job = find(job_id)
    _append_note(job, "cancelled", notes, at)
    job.status = "cancelled"
    job.finished = at
    _move(job, paths.done_dir())
    log("cancel", job, at=at)
    return job


def edit(
    job_id: str,
    *,
    title: str | None = None,
    notes: str | None = None,
    append_notes: str | None = None,
    at: datetime | None = None,
    cron: str | None = None,
    condition: str | None = None,
    every: str | None = None,
    expires: datetime | None = None,
    folder: str | None = None,
    branch: str | None = None,
    when: datetime | None = None,
) -> Job:
    when = when or now()
    job = find(job_id)
    changed = []
    if title is not None:
        job.title = title.strip()
        changed.append("title")
    if notes is not None:
        job.notes = notes if notes.endswith("\n") or not notes else notes + "\n"
        changed.append("notes")
    if append_notes:
        _append_note(job, "note", append_notes, when)
        changed.append("notes")
    if cron is not None:
        if job.kind != "repeat":
            raise JcronError("only repeat jobs have a cron rule")
        schedule.validate_cron(cron)
        job.repeat = cron
        if at is None:
            job.due = schedule.next_cron(cron, when)
        changed.append("cron")
    if condition is not None or every is not None:
        if job.kind != "check":
            raise JcronError("only check jobs have a condition or interval")
        if condition is not None:
            job.condition = condition
            changed.append("condition")
        if every is not None:
            parse_duration(every)
            job.check_every = every
            changed.append("every")
    if expires is not None:
        if job.kind not in ("check", "todo"):
            raise JcronError("only check jobs and TODOs have an expiry")
        job.expires = expires
        changed.append("expires")
    if at is not None:
        if job.kind == "todo":
            raise JcronError("a TODO has no due time; change when it expires instead (expires)")
        job.due = at
        changed.append("due")
    if folder is not None:
        job.folder = str(Path(folder).resolve())
        changed.append("folder")
    if branch is not None:
        job.branch = branch or None
        changed.append("branch")
    if not changed:
        raise JcronError("nothing to change")
    _save(job)
    log("edit", job, "fields=" + ",".join(dict.fromkeys(changed)), at=when)
    return job
