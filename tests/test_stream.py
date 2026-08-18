"""
Tests for the streaming layer: request construction, the 14 field-builder helpers,
subscription bookkeeping across commands, and two fixes (None-parameter safety and
the StreamAsync.start_auto daemon leak). No websocket is opened.
"""
import asyncio
import datetime
import logging
import types

import pytest

import schwabdev.stream as stream_mod
from conftest import STREAMER_INFO

LOG = logging.getLogger("schwabdev-tests")


# ----------------------------- basic_request ------------------------------ #
class TestBasicRequest:
    def test_shape_and_case_folding(self, stream_base):
        stream_base._request_id = 0
        req = stream_base.basic_request("levelone_equities", "add",
                                        {"keys": "AAPL", "fields": "0,1"})
        assert req == {
            "service": "LEVELONE_EQUITIES", "command": "ADD", "requestid": 1,
            "SchwabClientCustomerId": "CUST", "SchwabClientCorrelId": "CORR",
            "parameters": {"keys": "AAPL", "fields": "0,1"}}

    def test_request_id_increments(self, stream_base):
        stream_base._request_id = 0
        a = stream_base.basic_request("ADMIN", "LOGOUT")
        b = stream_base.basic_request("ADMIN", "LOGOUT")
        assert (a["requestid"], b["requestid"]) == (1, 2)
        assert "parameters" not in a  # no parameters key when none supplied

    def test_none_parameter_values_are_stripped(self, stream_base):
        # Regression: a None-valued parameter must be dropped cleanly (the old code
        # mutated the dict mid-iteration and raised RuntimeError).
        req = stream_base.basic_request(
            "LEVELONE_EQUITIES", "ADD",
            {"keys": "AAPL", "fields": None, "extra": None})
        assert req["parameters"] == {"keys": "AAPL"}


# ----------------------------- field builders ----------------------------- #
BUILDERS = [
    ("level_one_equities",        (["AAPL", "GOOG"], "0,1,2", "ADD"),   "LEVELONE_EQUITIES",        "AAPL,GOOG", "0,1,2", "ADD"),
    ("level_one_options",         (["GOOG  240809C00095000"], [0, 1], "SUBS"), "LEVELONE_OPTIONS", "GOOG  240809C00095000", "0,1", "SUBS"),
    ("level_one_futures",         ("/ESF24", "0,1", "ADD"),             "LEVELONE_FUTURES",         "/ESF24", "0,1", "ADD"),
    ("level_one_futures_options", (["./OZCZ23C565"], "0", "ADD"),       "LEVELONE_FUTURES_OPTIONS", "./OZCZ23C565", "0", "ADD"),
    ("level_one_forex",           ("EUR/USD", "0,1,2", "UNSUBS"),       "LEVELONE_FOREX",           "EUR/USD", "0,1,2", "UNSUBS"),
    ("nyse_book",                 (["NIO", "F"], "0,1", "ADD"),         "NYSE_BOOK",                "NIO,F", "0,1", "ADD"),
    ("nasdaq_book",               ("AMD", "0", "ADD"),                  "NASDAQ_BOOK",              "AMD", "0", "ADD"),
    ("options_book",              (["AAPL  240517P00190000"], "0", "VIEW"), "OPTIONS_BOOK",         "AAPL  240517P00190000", "0", "VIEW"),
    ("chart_equity",              (["GOOG"], "0,1,2", "ADD"),           "CHART_EQUITY",             "GOOG", "0,1,2", "ADD"),
    ("chart_futures",             ("/ESF24", "0,1", "ADD"),             "CHART_FUTURES",            "/ESF24", "0,1", "ADD"),
    ("screener_equity",           (["$DJI_PERCENT_CHANGE_UP_60"], "0", "ADD"), "SCREENER_EQUITY",   "$DJI_PERCENT_CHANGE_UP_60", "0", "ADD"),
    ("screener_options",          (["OPTION_PUT_TRADES_30"], "0,1", "ADD"), "SCREENER_OPTION",      "OPTION_PUT_TRADES_30", "0,1", "ADD"),
]


@pytest.mark.parametrize("name,args,service,keys,fields,command", BUILDERS,
                         ids=[b[0] for b in BUILDERS])
def test_field_builder(stream_base, name, args, service, keys, fields, command):
    stream_base._request_id = 0
    req = getattr(stream_base, name)(*args)
    assert req == {
        "service": service, "command": command, "requestid": 1,
        "SchwabClientCustomerId": "CUST", "SchwabClientCorrelId": "CORR",
        "parameters": {"keys": keys, "fields": fields}}


def test_account_activity_defaults(stream_base):
    stream_base._request_id = 0
    req = stream_base.account_activity()
    assert req["service"] == "ACCT_ACTIVITY"
    assert req["command"] == "SUBS"
    assert req["parameters"] == {"keys": "Account Activity", "fields": "0,1,2,3"}


# --------------------------- _record_request ------------------------------ #
def test_record_request_command_sequence(stream_base):
    def fields_as_sets(subs):
        return {svc: {k: set(v) for k, v in keys.items()} for svc, keys in subs.items()}

    steps = [
        {"service": "LEVELONE_EQUITIES", "command": "ADD",
         "parameters": {"keys": "AAPL,GOOG", "fields": "0,1,2"}},
        {"service": "LEVELONE_EQUITIES", "command": "ADD",   # overlap merges fields for AAPL
         "parameters": {"keys": "AAPL", "fields": "2,3,4"}},
        {"service": "LEVELONE_EQUITIES", "command": "VIEW",  # reset every key's fields
         "parameters": {"keys": "", "fields": "9"}},
        {"service": "LEVELONE_EQUITIES", "command": "UNSUBS",
         "parameters": {"keys": "GOOG", "fields": "0"}},
        {"service": "LEVELONE_OPTIONS", "command": "SUBS",
         "parameters": {"keys": "X,Y", "fields": "0,1"}},
        {"service": "LEVELONE_OPTIONS", "command": "SUBS",   # SUBS replaces wholesale
         "parameters": {"keys": "Z", "fields": "5"}},
    ]
    for step in steps:
        stream_base._record_request(step)

    assert fields_as_sets(stream_base.subscriptions) == {
        "LEVELONE_EQUITIES": {"AAPL": {"9"}},   # GOOG unsubbed; VIEW reset AAPL's fields to ["9"]
        "LEVELONE_OPTIONS": {"Z": {"5"}},        # last SUBS replaced X/Y
    }


def test_record_request_ignores_malformed(stream_base):
    stream_base._record_request({"service": "X"})            # no parameters -> ignored
    stream_base._record_request({"command": "ADD", "parameters": {}})  # no service -> ignored
    assert stream_base.subscriptions == {}


# ---------------------- StreamAsync.start_auto fix ------------------------ #
def _fake_client():
    c = types.SimpleNamespace()
    c.tokens = types.SimpleNamespace(access_token="AT")
    c.logger = LOG
    c._get_streamer_info = lambda: STREAMER_INFO
    return c


async def test_start_auto_does_not_leak_daemon():
    # Regression: StreamAsync.start_auto must not forward `daemon` into the receiver
    # path (StreamAsync.start has no daemon param; leaking it crashed non-print receivers).
    s = stream_mod.StreamAsync(_fake_client())
    captured = {}
    called = []

    async def fake_run_streamer(receiver_func=print, ping_timeout=30, **kwargs):
        called.append(True)
        captured.update(kwargs)
        s.active = True  # stop the checker from re-entering start()

    s._run_streamer = fake_run_streamer
    # All weekdays + full-day window so the active-window check is true regardless of
    # the checker's timezone (it evaluates "now" in America/New_York).
    await s.start_auto(receiver=print,
                       start_time=datetime.time(0, 0, 0),
                       stop_time=datetime.time(23, 59, 59),
                       on_days=list(range(7)))
    for _ in range(100):  # let the scheduled checker tick fire start() -> _run_streamer
        if called:
            break
        await asyncio.sleep(0)
    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        task.cancel()
    await asyncio.sleep(0)

    assert called, "start_auto did not start the stream within the active window"
    assert "daemon" not in captured
