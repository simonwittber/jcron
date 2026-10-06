import pytest


@pytest.fixture(autouse=True)
def jcron_home(tmp_path, monkeypatch):
    home = tmp_path / "jcron"
    monkeypatch.setenv("JCRON_HOME", str(home))
    return home
