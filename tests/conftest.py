import pytest


@pytest.fixture(autouse=True)
def jcron_home(tmp_path, monkeypatch):
    home = tmp_path / "jcron"
    monkeypatch.setenv("JCRON_HOME", str(home))
    # Mark the weekly stale report as just done, far in the future, so it stays out of tests that are not about it.
    home.mkdir(parents=True)
    (home / "last-stale-report.txt").write_text("2100-01-01T00:00:00+00:00\n", encoding="utf-8")
    return home
