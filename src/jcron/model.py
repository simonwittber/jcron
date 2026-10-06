"""The job record and its YAML form."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field, fields
from datetime import date, datetime, time
from pathlib import Path

import yaml

from .timeparse import to_local

KINDS = ("reminder", "repeat", "check")
TIME_FIELDS = ("created", "due", "expires", "condition_met", "claimed_at", "last_done", "finished")
TEXT_FIELDS = ("id", "kind", "title", "status", "folder", "branch", "repeat", "condition", "check_every", "claimed_by")


@dataclass
class Job:
    id: str
    kind: str
    title: str
    status: str = "waiting"
    created: datetime | None = None
    folder: str | None = None
    branch: str | None = None
    due: datetime | None = None
    repeat: str | None = None
    condition: str | None = None
    check_every: str | None = None
    expires: datetime | None = None
    condition_met: datetime | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    last_done: datetime | None = None
    finished: datetime | None = None
    notes: str = ""
    # Keys jcron does not know about, kept so hand edits survive a save.
    extra: dict = field(default_factory=dict)
    # Where the file was loaded from; not saved.
    path: Path | None = field(default=None, compare=False)

    def to_dict(self) -> dict:
        data = {}
        for f in fields(self):
            if f.name in ("extra", "path", "notes"):
                continue
            value = getattr(self, f.name)
            if value is not None:
                data[f.name] = value
        data.update(self.extra)
        data["notes"] = self.notes
        return data

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)

    @classmethod
    def from_yaml(cls, text: str, path: Path | None = None) -> Job:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("job file is not a YAML mapping")
        known = {f.name for f in fields(cls)} - {"extra", "path"}
        values = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        for name in ("id", "kind", "title"):
            if values.get(name) is None:
                raise ValueError(f"job file has no {name!r}")
        for name in TIME_FIELDS:
            if values.get(name) is not None:
                values[name] = _as_time(values[name])
        # YAML may read a branch like "1.0" as a number, so force text fields back to strings.
        for name in TEXT_FIELDS:
            if values.get(name) is not None:
                values[name] = str(values[name])
        values["notes"] = str(values.get("notes") or "")
        return cls(**values, extra=extra, path=path)


def make_id(title: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", title.lower()))[:32].strip("-") or "job"
    return f"{slug}-{secrets.token_hex(2)}"


def _as_time(value) -> datetime:
    if isinstance(value, datetime):
        return to_local(value)
    if isinstance(value, date):
        return to_local(datetime.combine(value, time()))
    return to_local(datetime.fromisoformat(str(value)))


class _Dumper(yaml.SafeDumper):
    pass


def _represent_datetime(dumper: yaml.SafeDumper, value: datetime):
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", value.isoformat(timespec="seconds"))


def _represent_str(dumper: yaml.SafeDumper, value: str):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_Dumper.add_representer(datetime, _represent_datetime)
_Dumper.add_representer(str, _represent_str)
