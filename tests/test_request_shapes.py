"""
Regression tests that pin the exact HTTP call each REST endpoint builds
(method, path, query params, JSON body, special headers). These lock the
request contract so a future refactor cannot silently change the wire format.

Note the deliberate sync/async differences that are part of the public behavior:
  - booleans are sent as Python bools on the sync client, but as "true"/"false"
    strings on the async client;
  - market_hours sends a joined "equity,option" string on sync, but a raw list
    on async.
"""
import datetime

import pytest

from conftest import ACCOUNT_HASH

DT = datetime.datetime(2024, 3, 5, 9, 30, 45, 123456, tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- #
# Sync                                                                          #
# --------------------------------------------------------------------------- #
SYNC_CASES = [
    ("linked_accounts", (), {},
     {"method": "GET", "path": "/trader/v1/accounts/accountNumbers",
      "params": None, "json": None, "headers": None}),
    ("account_details", (ACCOUNT_HASH,), {"fields": "positions"},
     {"method": "GET", "path": f"/trader/v1/accounts/{ACCOUNT_HASH}",
      "params": {"fields": "positions"}, "json": None, "headers": None}),
    ("quotes", (["AMD", "INTC"],), {"fields": "all", "indicative": True},
     {"method": "GET", "path": "/marketdata/v1/quotes",
      "params": {"fields": "all", "indicative": True, "symbols": "AMD,INTC"},
      "json": None, "headers": None}),
    ("price_history", ("AAPL",),
     {"periodType": "day", "startDate": DT, "endDate": DT,
      "needExtendedHoursData": True, "needPreviousClose": False},
     {"method": "GET", "path": "/marketdata/v1/pricehistory",
      "params": {"endDate": 1709631045123, "needExtendedHoursData": True,
                 "needPreviousClose": False, "periodType": "day",
                 "startDate": 1709631045123, "symbol": "AAPL"},
      "json": None, "headers": None}),
    ("option_chains", ("AAPL",),
     {"contractType": "CALL", "strikeCount": 5, "includeUnderlyingQuote": True,
      "fromDate": DT, "toDate": DT},
     {"method": "GET", "path": "/marketdata/v1/chains",
      "params": {"contractType": "CALL", "fromDate": "2024-03-05",
                 "includeUnderlyingQuote": True, "strikeCount": 5,
                 "symbol": "AAPL", "toDate": "2024-03-05"},
      "json": None, "headers": None}),
    ("instruments", ("AAPL", "symbol-search"), {},
     {"method": "GET", "path": "/marketdata/v1/instruments",
      "params": {"projection": "symbol-search", "symbol": "AAPL"},
      "json": None, "headers": None}),
    ("market_hours", (["equity", "option"],), {"date": DT},
     {"method": "GET", "path": "/marketdata/v1/markets",
      "params": {"date": "2024-03-05", "markets": "equity,option"},
      "json": None, "headers": None}),
    ("movers", ("$DJI",), {"sort": "VOLUME", "frequency": 5},
     {"method": "GET", "path": "/marketdata/v1/movers/$DJI",
      "params": {"frequency": 5, "sort": "VOLUME"},
      "json": None, "headers": {"accept": "application/json"}}),
    ("place_order", (ACCOUNT_HASH, {"x": 1}), {},
     {"method": "POST", "path": f"/trader/v1/accounts/{ACCOUNT_HASH}/orders",
      "params": None, "json": {"x": 1},
      "headers": {"Accept": "application/json", "Content-Type": "application/json"}}),
]


@pytest.mark.parametrize("name,args,kwargs,expected", SYNC_CASES,
                         ids=[c[0] for c in SYNC_CASES])
def test_sync_endpoint_shape(sync_client, name, args, kwargs, expected):
    client, calls = sync_client
    getattr(client, name)(*args, **kwargs)
    assert calls == [expected]


def test_place_order_returns_raw_response(sync_client):
    # place_order must return the raw Response (the caller reads the order id header),
    # not a parsed body.
    from conftest import RecordingResponse
    client, _ = sync_client
    result = client.place_order(ACCOUNT_HASH, {"x": 1})
    assert isinstance(result, RecordingResponse)


# --------------------------------------------------------------------------- #
# Async                                                                         #
# --------------------------------------------------------------------------- #
ASYNC_CASES = [
    ("quotes", (["AMD", "INTC"],), {"fields": "all", "indicative": True},
     {"method": "GET", "path": "/marketdata/v1/quotes",
      "params": {"fields": "all", "indicative": "true", "symbols": "AMD,INTC"},
      "json": None, "headers": None}),
    ("price_history", ("AAPL",),
     {"periodType": "day", "startDate": DT, "endDate": DT,
      "needExtendedHoursData": True, "needPreviousClose": False},
     {"method": "GET", "path": "/marketdata/v1/pricehistory",
      "params": {"endDate": 1709631045123, "needExtendedHoursData": "true",
                 "needPreviousClose": "false", "periodType": "day",
                 "startDate": 1709631045123, "symbol": "AAPL"},
      "json": None, "headers": None}),
    # market_hours sends a raw list on the async client (documented difference).
    ("market_hours", (["equity", "option"],), {"date": DT},
     {"method": "GET", "path": "/marketdata/v1/markets",
      "params": {"date": "2024-03-05", "markets": ["equity", "option"]},
      "json": None, "headers": None}),
]


@pytest.mark.parametrize("name,args,kwargs,expected", ASYNC_CASES,
                         ids=[c[0] for c in ASYNC_CASES])
async def test_async_endpoint_shape(async_client, name, args, kwargs, expected):
    client, calls = async_client
    await getattr(client, name)(*args, **kwargs)
    assert calls == [expected]


async def test_async_place_order_shape_and_raw_response(async_client):
    from conftest import AsyncRecordingResponse
    client, calls = async_client
    result = await client.place_order(ACCOUNT_HASH, {"x": 1})
    assert calls == [{
        "method": "POST", "path": f"/trader/v1/accounts/{ACCOUNT_HASH}/orders",
        "params": None, "json": {"x": 1},
        "headers": {"Accept": "application/json", "Content-Type": "application/json"}}]
    assert isinstance(result, AsyncRecordingResponse)
