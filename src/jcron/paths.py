"""Where jcron keeps its files."""

import os
from pathlib import Path


# The folder inside a repo that holds shared jobs, committed with the branch.
SHARED_DIRNAME = ".jcron"


def home() -> Path:
    override = os.environ.get("JCRON_HOME")
    return Path(override).expanduser() if override else Path.home() / ".jcron"


def jobs_dir() -> Path:
    return home() / "jobs"


def claimed_dir() -> Path:
    return home() / "claimed"


def done_dir() -> Path:
    return home() / "done"


def seen_dir() -> Path:
    return home() / "seen"


def log_file() -> Path:
    return home() / "log.txt"


def ensure() -> None:
    for folder in (jobs_dir(), claimed_dir(), done_dir(), seen_dir()):
        folder.mkdir(parents=True, exist_ok=True)
