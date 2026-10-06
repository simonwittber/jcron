"""The Claude Code hook that reports due jobs, and its installer."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from . import paths, store
from .display import due_report
from .model import Job
from .timeparse import fmt, now

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit")
SEEN_MAX_AGE_SECONDS = 7 * 86400


def _seen_key(job: Job) -> str:
    # Include the due time, so the next run of a repeat job or the next check gets reported again.
    return f"{job.id}@{fmt(job.due) if job.due else '-'}"


def _prune_seen() -> None:
    cutoff = time.time() - SEEN_MAX_AGE_SECONDS
    for path in paths.seen_dir().glob("*.txt"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def run(stdin_text: str, at: datetime | None = None) -> str:
    """Return the text to add to the session, or an empty string when nothing new is due."""
    at = at or now()
    try:
        event = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    jobs = store.due_jobs(at)
    session = event.get("session_id")
    if session:
        seen_path = paths.seen_dir() / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', str(session))}.txt"
        seen = set(seen_path.read_text(encoding="utf-8").split()) if seen_path.exists() else set()
        # A session start (including resume and compaction) may have lost earlier reports, so repeat them all.
        if event.get("hook_event_name") != "SessionStart":
            jobs = [j for j in jobs if _seen_key(j) not in seen]
        new_keys = [_seen_key(j) for j in jobs if _seen_key(j) not in seen]
        if new_keys:
            with seen_path.open("a", encoding="utf-8") as f:
                f.write("".join(k + "\n" for k in new_keys))
        _prune_seen()
    return due_report(jobs, at) if jobs else ""


def install(settings_path: Path, command: str, confirm) -> str:
    """Add the hook to a Claude Code settings file, after showing the change and asking."""
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    added = []
    for event in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        present = any(h.get("command") == command for g in groups for h in g.get("hooks", []))
        if not present:
            groups.append({"hooks": [{"type": "command", "command": command}]})
            added.append(event)
    if not added:
        return f"The hook is already installed in {settings_path}."
    preview = json.dumps({e: hooks[e] for e in added}, indent=2)
    if not confirm(f"Add to {settings_path} under \"hooks\":\n{preview}\n"):
        return "Nothing changed."
    if settings_path.exists():
        backup = settings_path.with_suffix(settings_path.suffix + ".bak")
        backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return f"Installed the hook for {', '.join(added)} in {settings_path}."
