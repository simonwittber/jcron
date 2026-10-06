from datetime import datetime, timedelta

import pytest

from jcron.timeparse import format_duration, parse_duration, parse_when, relative, to_local

BASE = to_local(datetime(2026, 10, 6, 12, 0, 0))


def test_durations():
    assert parse_duration("30m") == timedelta(minutes=30)
    assert parse_duration("1h30m") == timedelta(hours=1, minutes=30)
    assert parse_duration("2d") == timedelta(days=2)
    assert parse_duration("1w") == timedelta(weeks=1)
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_format_duration():
    assert format_duration(timedelta(hours=1, minutes=30)) == "1h30m"
    assert format_duration(timedelta(days=2, hours=3, minutes=5)) == "2d3h"


@pytest.mark.parametrize("text, expected", [
    ("in 2h", BASE + timedelta(hours=2)),
    ("+30m", BASE + timedelta(minutes=30)),
    ("45m", BASE + timedelta(minutes=45)),
    ("now", BASE),
])
def test_short_relative_times(text, expected):
    assert parse_when(text, BASE) == expected


def test_natural_language_times_are_local():
    tomorrow = parse_when("tomorrow 9am", BASE)
    assert (tomorrow.year, tomorrow.month, tomorrow.day, tomorrow.hour) == (2026, 10, 7, 9)
    assert tomorrow.utcoffset() == to_local(datetime(2026, 10, 7, 9)).utcoffset()
    assert parse_when("in 2 hours", BASE) == BASE + timedelta(hours=2)


def test_iso_times_convert_to_local():
    value = parse_when("2026-10-06T00:00:00+00:00", BASE)
    assert value.utcoffset() == to_local(value).utcoffset()
    assert value == datetime.fromisoformat("2026-10-06T00:00:00+00:00")


def test_bad_time():
    with pytest.raises(ValueError):
        parse_when("when pigs fly", BASE)


def test_relative_text():
    assert relative(BASE + timedelta(hours=2), BASE) == "in 2h"
    assert relative(BASE - timedelta(minutes=5), BASE) == "5m ago"
