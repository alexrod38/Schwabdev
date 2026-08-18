"""
Tests for endpoint parameter validation: type checks, enum/range checks,
multi-type acceptance, and the Client(checks=False) bypass. Validation lives on
ClientBase, so the sync and async clients share it (a couple of async tests
confirm parity).
"""
import datetime

import pytest

from conftest import build_recording_client, ACCOUNT_HASH

UTC = datetime.timezone.utc
DT = datetime.datetime(2024, 3, 5, 9, 30, 45, tzinfo=UTC)


@pytest.fixture
def client():
    c, calls = build_recording_client(is_async=False)
    return c, calls


# --------------------------------------------------------------------------- #
# Type errors                                                                   #
# --------------------------------------------------------------------------- #
TYPE_ERRORS = [
    ("quotes", (123,), {}),                                  # symbols not str/list
    ("quotes", ("AAPL",), {"indicative": "yes"}),           # indicative not bool
    ("account_details", (123,), {}),                        # accountHash not str
    ("price_history", (123,), {}),                          # symbol not str
    ("price_history", ("AAPL",), {"frequency": 1.5}),       # frequency not int
    ("option_chains", ("AAPL",), {"strikeCount": 1.5}),     # strikeCount not int
    ("option_chains", ("AAPL",), {"strike": "x"}),          # strike not number
    ("order_details", (ACCOUNT_HASH, 1.5), {}),                   # orderId not int/str
    ("market_hours", (["equity"],), {"date": 20240305}),    # date int not allowed (ISO date param)
    ("place_order", (ACCOUNT_HASH, "not-a-dict"), {}),            # order not dict
    ("account_orders", (ACCOUNT_HASH, None, DT), {}),             # required fromEnteredTime is None
]


@pytest.mark.parametrize("name,args,kwargs", TYPE_ERRORS,
                         ids=[f"{c[0]}:{i}" for i, c in enumerate(TYPE_ERRORS)])
def test_type_errors(client, name, args, kwargs):
    c, _ = client
    with pytest.raises(TypeError):
        getattr(c, name)(*args, **kwargs)


# --------------------------------------------------------------------------- #
# Value / enum / range errors                                                   #
# --------------------------------------------------------------------------- #
VALUE_ERRORS = [
    ("quotes", ("AAPL",), {"fields": "bogus"}),                 # not a quote field
    ("account_details", (ACCOUNT_HASH,), {"fields": "bogus"}),        # not "positions"
    ("option_chains", ("AAPL",), {"contractType": "BUY"}),      # bad enum
    ("option_chains", ("AAPL",), {"strategy": "BOGUS"}),
    ("option_chains", ("AAPL",), {"expMonth": "JANUARY"}),
    ("option_chains", ("AAPL",), {"entitlement": "ALL"}),       # only PN/NP/PP
    ("option_chains", ("AAPL",), {"strikeCount": 0}),           # below min (1)
    ("price_history", ("AAPL",), {"periodType": "decade"}),
    ("price_history", ("AAPL",), {"periodType": "day", "period": 7}),          # day allows 1,2,3,4,5,10
    ("price_history", ("AAPL",), {"periodType": "day", "frequencyType": "weekly"}),  # day -> minute only
    ("price_history", ("AAPL",), {"frequencyType": "minute", "frequency": 2}),  # minute -> 1,5,10,15,30
    ("movers", ("BOGUS",), {}),
    ("movers", ("$DJI",), {"sort": "BOGUS"}),
    ("movers", ("$DJI",), {"frequency": 3}),                    # not in {0,1,5,10,30,60}
    ("market_hours", (["equity", "crypto"],), {}),              # crypto not a market
    ("market_hour", ("crypto",), {}),
    ("instruments", ("AAPL", "bogus"), {}),                     # bad projection
    ("account_orders", (ACCOUNT_HASH, DT, DT), {"status": "BOGUS"}),
    ("account_orders", (ACCOUNT_HASH, DT, DT), {"maxResults": 0}),    # below min (1)
    ("transactions", (ACCOUNT_HASH, DT, DT, "BOGUS"), {}),            # bad transaction type
]


@pytest.mark.parametrize("name,args,kwargs", VALUE_ERRORS,
                         ids=[f"{c[0]}:{i}" for i, c in enumerate(VALUE_ERRORS)])
def test_value_errors(client, name, args, kwargs):
    c, _ = client
    with pytest.raises(ValueError):
        getattr(c, name)(*args, **kwargs)


# --------------------------------------------------------------------------- #
# Multi-type acceptance: schwabdev accepts several types for some parameters    #
# --------------------------------------------------------------------------- #
ACCEPTED = [
    ("quotes", (["AMD", "INTC"],), {}),          # symbols as list
    ("quotes", ("AMD,INTC",), {}),               # symbols as str
    ("quotes", (("AMD", "INTC"),), {}),          # symbols as tuple
    ("price_history", ("AAPL",), {"startDate": DT}),                 # datetime
    ("price_history", ("AAPL",), {"startDate": datetime.date(2024, 3, 5)}),  # date
    ("price_history", ("AAPL",), {"startDate": "2024-03-05"}),       # str
    ("price_history", ("AAPL",), {"startDate": 1709631045123}),      # epoch int
    ("order_details", (ACCOUNT_HASH, 12345), {}),      # orderId int
    ("order_details", (ACCOUNT_HASH, "12345"), {}),    # orderId str
    ("instrument_cusip", (37833100,), {}),       # cusip int
    ("instrument_cusip", ("037833100",), {}),    # cusip str
    ("market_hours", (["equity"],), {"date": datetime.date(2024, 3, 5)}),  # date as date
    ("option_chains", ("AAPL",), {"fromDate": datetime.date(2024, 3, 5)}),
    ("price_history", ("AAPL",), {"periodType": "day", "period": 10}),       # valid combo
    ("price_history", ("AAPL",), {"frequencyType": "minute", "frequency": 5}),
]


@pytest.mark.parametrize("name,args,kwargs", ACCEPTED,
                         ids=[f"{c[0]}:{i}" for i, c in enumerate(ACCEPTED)])
def test_accepted_inputs_pass(client, name, args, kwargs):
    c, calls = client
    getattr(c, name)(*args, **kwargs)   # must not raise
    assert len(calls) == 1              # and must reach the request layer


# --------------------------------------------------------------------------- #
# checks=False bypass                                                           #
# --------------------------------------------------------------------------- #
def test_checks_disabled_skips_all_validation():
    c, calls = build_recording_client(is_async=False)
    c._validator.enabled = False  # equivalent to Client(validate_params=False)
    # All of these would normally raise; with checks off they pass straight through.
    c.quotes(123, fields="bogus", indicative="yes")
    c.movers("BOGUS", sort="NONSENSE", frequency=999)
    c.option_chains("AAPL", contractType="BUY", strikeCount=-5)
    assert len(calls) == 3


def test_checks_flag_set_by_default():
    c, _ = build_recording_client(is_async=False)
    assert c._validator.enabled is True


def test_short_account_hash_rejected(client):
    # The client guards against passing the short account *number* where the long
    # *hashValue* (from linked_accounts()) is required.
    c, _ = client
    with pytest.raises(ValueError):
        c.account_details("12345678")  # < 14 chars


# --------------------------------------------------------------------------- #
# Async parity (validation lives on the shared base)                            #
# --------------------------------------------------------------------------- #
async def test_async_type_error():
    c, _ = build_recording_client(is_async=True)
    with pytest.raises(TypeError):
        await c.quotes("AAPL", indicative="yes")


async def test_async_value_error():
    c, _ = build_recording_client(is_async=True)
    with pytest.raises(ValueError):
        await c.movers("BOGUS")


async def test_async_valid_passes():
    c, calls = build_recording_client(is_async=True)
    await c.price_history("AAPL", periodType="day", period=10)
    assert len(calls) == 1
