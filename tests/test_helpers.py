"""
Pure helper functions on ClientBase / StreamBase: time conversion, list joining,
param parsing. These need no network or session.
"""
import datetime
import logging
import threading
import types

import pytest

from schwabdev.client import Client
from schwabdev.utils import TimeFormat

UTC = datetime.timezone.utc


@pytest.fixture
def base():
    """A bare ClientBase-capable instance for calling pure helpers.

    Minimal attributes are set so the client's __del__/close() stays quiet when
    the instance is garbage-collected (it never opened a real session).
    """
    c = Client.__new__(Client)
    c.logger = logging.getLogger("schwabdev-tests")
    c._session_lock = threading.RLock()
    c._session = types.SimpleNamespace(close=lambda: None)
    return c


# --------------------------- _time_convert -------------------------------- #
class TestTimeConvert:
    DT_US = datetime.datetime(2024, 3, 5, 9, 30, 45, 123456, tzinfo=UTC)

    @pytest.mark.parametrize("fmt,expected", [
        (TimeFormat.ISO_8601, "2024-03-05T09:30:45.123Z"),
        (TimeFormat.EPOCH, 1709631045),
        (TimeFormat.EPOCH_MS, 1709631045123),
        (TimeFormat.YYYY_MM_DD, "2024-03-05"),
    ])
    def test_datetime_with_microseconds(self, base, fmt, expected):
        assert base._time_convert(self.DT_US, fmt) == expected

    @pytest.mark.parametrize("value", ["2024-01-01T00:00:00Z", "passthrough", None])
    @pytest.mark.parametrize("fmt", list(TimeFormat))
    def test_str_and_none_passthrough(self, base, value, fmt):
        assert base._time_convert(value, fmt) == value

    def test_whole_second_datetime_keeps_seconds(self, base):
        # Regression: a whole-second datetime must not drop the seconds in ISO 8601.
        dt = datetime.datetime(2024, 3, 5, 9, 30, 45, tzinfo=UTC)
        assert base._time_convert(dt, TimeFormat.ISO_8601) == "2024-03-05T09:30:45.000Z"

    @pytest.mark.parametrize("offset,local_time", [
        (datetime.timedelta(hours=-5), (2024, 3, 5, 4, 30, 45, 123456)),
        (datetime.timedelta(hours=5, minutes=30), (2024, 3, 5, 15, 0, 45, 123456)),
    ])
    def test_offset_aware_datetime_is_normalized_to_utc(self, base, offset, local_time):
        # Regression: appending Z without normalization mislabeled local time as UTC.
        dt = datetime.datetime(*local_time, tzinfo=datetime.timezone(offset))
        assert base._time_convert(dt, TimeFormat.ISO_8601) == "2024-03-05T09:30:45.123Z"

    def test_bare_date_iso_and_epoch(self, base):
        # Regression: a datetime.date must convert (as midnight UTC), not raise.
        d = datetime.date(2024, 3, 5)
        assert base._time_convert(d, TimeFormat.ISO_8601) == "2024-03-05T00:00:00.000Z"
        assert base._time_convert(d, TimeFormat.EPOCH_MS) == \
            int(datetime.datetime(2024, 3, 5, tzinfo=UTC).timestamp() * 1000)
        assert base._time_convert(d, TimeFormat.YYYY_MM_DD) == "2024-03-05"

    def test_string_format_values_accepted(self, base):
        # The format may be given as the enum's raw string value.
        assert base._time_convert(self.DT_US, TimeFormat.EPOCH.value) == 1709631045

    def test_unknown_format_raises(self, base):
        with pytest.raises(ValueError):
            base._time_convert(self.DT_US, "not-a-format")


# --------------------------- _format_list --------------------------------- #
class TestFormatList:
    @pytest.mark.parametrize("value,expected", [
        (["AMD", "INTC"], "AMD,INTC"),
        (("AMD", "INTC"), "AMD,INTC"),
        ([1, 2, 3], "1,2,3"),
        ("AMD,INTC", "AMD,INTC"),   # string passes through
        (None, None),              # None preserved for the params parser
    ])
    def test_format_list(self, base, value, expected):
        assert base._format_list(value) == expected


# --------------------------- _parse_params -------------------------------- #
class TestParseParams:
    def test_drops_none_values(self, base):
        out = base._parse_params({"a": 1, "b": None, "c": "x", "d": None})
        assert out == {"a": 1, "c": "x"}

    def test_keeps_falsey_non_none(self, base):
        # 0, False, and "" are real values and must be preserved.
        out = base._parse_params({"zero": 0, "flag": False, "empty": ""})
        assert out == {"zero": 0, "flag": False, "empty": ""}

    def test_returns_new_dict(self, base):
        src = {"a": 1, "b": None}
        out = base._parse_params(src)
        assert out is not src
