"""Turning user and LLM input into local times and durations."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_DURATION_PART = re.compile(r"(\d+)\s*([wdhms])")
_DURATION = re.compile(r"^(?:\s*\d+\s*[wdhms])+\s*$")
_RELATIVE = re.compile(r"^(?:in\s+|\+)(.+)$")


def now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def to_local(value: datetime) -> datetime:
    """Convert to local time with the UTC offset that applies at that moment.
    Naive times are taken to be local already."""
    return value.astimezone().replace(microsecond=0)


def fmt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def parse_duration(text: str) -> timedelta:
    cleaned = text.strip().lower()
    if not _DURATION.match(cleaned):
        raise ValueError(f"not a duration: {text!r} (use forms like 30m, 2h, 1d, 1h30m)")
    return timedelta(seconds=sum(int(n) * _UNITS[unit] for n, unit in _DURATION_PART.findall(cleaned)))


def format_duration(value: timedelta, parts: int = 2) -> str:
    seconds = int(abs(value.total_seconds()))
    out = []
    for unit, size in _UNITS.items():
        if seconds >= size and len(out) < parts:
            out.append(f"{seconds // size}{unit}")
            seconds %= size
    return "".join(out) or "0s"


def parse_when(text: str, base: datetime | None = None) -> datetime:
    """Parse "in 2h", "+30m", "tomorrow 9am", "friday 14:00" or an ISO time into local time."""
    base = base or now()
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered == "now":
        return base
    relative = _RELATIVE.match(lowered)
    if relative and _DURATION.match(relative.group(1)):
        return base + parse_duration(relative.group(1))
    if _DURATION.match(lowered):
        return base + parse_duration(lowered)
    try:
        return to_local(datetime.fromisoformat(cleaned))
    except ValueError:
        pass

    # dateparser is slow to import, so only load it when the simple forms above do not match.
    import dateparser

    result = dateparser.parse(
        cleaned,
        settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": base.replace(tzinfo=None)},
    )
    if result is None:
        raise ValueError(f"could not understand the time {text!r}")
    return to_local(result)


def relative(value: datetime, base: datetime) -> str:
    delta = value - base
    if abs(delta.total_seconds()) < 60:
        return "now"
    text = format_duration(timedelta(minutes=round(abs(delta.total_seconds()) / 60)))
    return f"in {text}" if delta.total_seconds() > 0 else f"{text} ago"


def human(value: datetime, base: datetime) -> str:
    return f"{value:%Y-%m-%d %H:%M} ({relative(value, base)})"
