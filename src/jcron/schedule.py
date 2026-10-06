"""Repeat rules (cron) for repeating jobs."""

from __future__ import annotations

from datetime import datetime

from .timeparse import to_local


def validate_cron(rule: str) -> None:
    from croniter import croniter

    if not croniter.is_valid(rule):
        raise ValueError(f"not a valid cron rule: {rule!r} (for example '0 9 * * 1-5' means 9am on weekdays)")


def next_cron(rule: str, after: datetime) -> datetime:
    """The first time the rule matches after the given time, in local time."""
    from croniter import croniter

    # Work in local wall-clock time, so "9am" stays 9am across daylight-saving changes.
    wall = to_local(after).replace(tzinfo=None)
    return to_local(croniter(rule, wall).get_next(datetime))
