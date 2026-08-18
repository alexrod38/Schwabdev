### Schwabdev Trader Context ([repo](https://github.com/tylerebowers/Schwabdev-Context))

Trader Context is a unified wrapper for backtesting and live trading. Write one strategy function. Backtest it on cached minute candles, paper-trade it on live data, or
deploy it against your real Schwab account - the strategy code is identical in all three. 

To install run: `pip install schwabdev[context]`

Before using please note the current limitations:

* Orders are single-leg equity only.
* Only MARKET, LIMIT and STOP orders are supported.
* Only BUY and SELL orders are supported.
* Backtesting is limited to 30 days (unless you record more, as all history is cached).
* You must record level 1 and level 2 data for backtesting, (candles are from price history).
* Candles are 1-minute OHLC+volume. 
* The unified context api is still under development and may change significantly between versions.


```python
from schwabdev import Client, Context
from strategy import Strategy # example

tickers = ["AMD", "INTC"] # what to test on

client = Client(...)
ctx = Context(client)
strat = Strategy(tickers)

# run a backtest
run = ctx.backtest(my_strategy, tickers, cash=10_000, history_days=30, plot=True)

# deploy for live data (in beta release)
run = ctx.deploy(my_strategy, tickers, cash=10_000, plot=True)
```

Candles are fetched from Schwab once and cached in SQLite (`~/.schwabdev/candles.db` by default),
so the second backtest over the same range hits no network at all.

## The strategy

A strategy is any callable `strategy(tc, events)`:

* **`tc`**: the trader context. Everything the strategy can see or do goes through it (below).
  The same object type is handed to you in backtest, paper and live, so a strategy cannot tell
  which mode it is running in.
* **`events`**: the batch of new market events for this tick, in chronological order. Events are
  plain dicts; every one carries a `"type"` tag telling you what it is:

  | `type` | kind | shape |
  |---|---|---|
  | `"c"`  | candle | `{"symbol", "time", "open", "high", "low", "close", "volume", "type": "c"}` |
  | `"l1"` | level-1 quote | `{"symbol", "time", "bid", "ask", "last", "bid_size", "ask_size", "type": "l1"}` |
  | `"l2"` | level-2 book | `{"symbol", "time", "bids": [...], "asks": [...], "type": "l2"}` |

  `time` is UNIX milliseconds. Quotes are *deltas* — unchanged fields arrive as `None`; read the
  merged latest quote from `tc.quotes[symbol]` instead of the raw event.

**One tick = one timestamp.** In a backtest, all events sharing the same timestamp are delivered
in a single call; Schwab stamps minute candles on the minute boundary, so every ticker's candle
for 09:31 arrives together. Live, a tick is one stream message.

### Choosing what wakes the strategy

`backtest()` and `deploy()` share three flags:

| flag | default | meaning |
|---|---|---|
| `chart`  | `True`  | minute candles wake the strategy |
| `level1` | `False` | level-1 quotes wake the strategy |
| `level2` | `False` | order-book snapshots wake the strategy |

Candles are **always ingested** regardless of `chart`, they settle simulated orders, price MARKET
orders and mark positions, the flag only controls whether they *wake* you. **Schwab has no history API for level-1/level-2, so in a backtest those replay only what you previously captured (see "Recording" below).**


## The trader context (`tc`)

Read:

| interface | function |
|---|---|
| `tc.candles[sym]` | candle history so far; latest is `tc.candles[sym][-1]` |
| `tc.quotes[sym]` | latest merged level-1 quote |
| `tc.books[sym]` | latest level-2 snapshot |
| `tc.positions[sym]` | shares owned (partial fills included; absent = flat) |
| `tc.cash` | spendable cash = settled cash − amount reserved by your open BUY orders |
| `tc.sellable(sym)` | shares free to sell = owned − shares committed to open SELL orders |
| `tc.portfolio_value()` | settled cash + positions marked to their latest close |
| `tc.orders` | the order ledger, `symbol -> id -> record` |
| `tc.starting_cash` | what the run began with |

Act:

| interface | function |
|---|---|
| `tc.order(order_dict)` | place an order (Schwab order format, below); returns the order id |
| `tc.cancel(order_id)` | cancel a resting order; returns `True` if it will be canceled |
| `tc.plots[name]` | append `(time, value)` points; each name becomes a dashed overlay on the chart |

Overlay naming: a name containing a ticker (e.g. `"sma20 AMD"`) draws only on that ticker's panel;
a name containing no ticker draws on every panel.

`tc.cash` and `tc.sellable()` are advisory; orders are not rejected for exceeding them, so check
before placing.


## Orders

`tc.order()` takes the standard Schwab order dict. Supported: **single-leg equity** orders of type
**MARKET**, **LIMIT**, **STOP** with instruction **BUY** or **SELL**, whole shares only. Anything
else (options, multi-leg, trailing, fractional) raises `ValueError` before it goes anywhere.

```python
def buy(sym, qty, **extra):        # a helper you'll probably write once
    return {"orderType": "MARKET", "session": "NORMAL", "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{"instruction": "BUY", "quantity": qty,
                                    "instrument": {"symbol": sym, "assetType": "EQUITY"}}],
            **extra}

tc.order(buy("AMD", 10))                                  # market
tc.order({**buy("AMD", 10), "orderType": "LIMIT", "price": 98.50})
tc.order({**sell("AMD", 10), "orderType": "STOP", "stopPrice": 95.00})
```

### How simulated fills work

Placing an order records it as OPEN — reserving cash (buys) or committing shares (sells) — and it
settles on a **later** tick, so a backtest order can never fill on the candle that triggered it:

* **MARKET**: fills at the open of the candle `fill_delay` bars after placement (default 2).
* **LIMIT**: rests until a later candle's open or close crosses the limit; fills at the limit.
* **STOP**: triggers intrabar off the candle's low (SELL) / high (BUY); fills at the stop, or at
  the open if the bar gapped through it (the worse price).

In live **paper** mode `fill_delay` is 0: MARKET fills immediately at the last price, LIMIT and
STOP rest until the real market touches them.

### Transaction costs

Simulated fills go through a cost model. The default charges 0.05 % of notional plus SEC/TAF
regulatory fees on sells; slippage and spread are off. Tune it per run:

```python
from schwabdev import Costs
run = ctx.backtest(strat, ["AMD"], costs=Costs(half_spread=0.0002, slip=0.0001, flat=0.0))
```

`Costs(flat, per_share, pct, half_spread, slip, sec_fee, taf_per_share)`: half-spread and slip
move the execution price against you; the rest are cash fees. A limit order is never filled through
its own price, whatever the slippage setting. Real broker fills are never charged — Schwab's own
commissions already apply.


## Backtesting

```python
run = ctx.backtest(strategy, tickers,
                      history_days=90, cash=10_000,
                      chart=True, level1=False, level2=False,
                      costs=None, fill_delay=2,
                      report=True, plot=False)
```

Returns a `BacktestContext`. Each run is self-contained — keep several to compare strategies or
parameter sets:

```python
runs = [ctx.backtest(s, ["AMD"], report=False) for s in strategies]
best = max(runs, key=lambda r: r.stats["net_return"])
```

* `run.report()`: reprint the text report.
* `run.stats`: the underlying dict: `net_return`, `max_drawdown`, `sharpe`, `realized_pnl`,
  `fees_paid`, `uniform_b&h`, and per-ticker `win_rate` / `profit_factor` / `returns` / `trades`.
* `run.equity`: the `(time, portfolio_value)` curve, one point per tick.
* `run.serve()`: browser charts (non-blocking); `run.plot()` — same, but blocks like
  `plt.show()`.

Closed trades are matched **FIFO at the share level**, so partial fills, scale-ins and scale-outs
are each accounted as their own round trips.

With `plot=True` the viewer opens *before* the replay and streams the backtest as it runs.


## Recording level-1 / level-2

Schwab offers no quote/book history, so capture it yourself and backtests will replay it:

```python
ctx.record(["AMD", "INTC"], chart=True, level1=True, level2=True)
```

Uses the stream's `start_auto`, so it opens and closes with market hours — leave the process
running and it records every trading day. Any `start_auto` kwargs pass through (`start_time`,
`stop_time`, `on_days`, ...); `verbose=False` silences the per-message counters. Recorded candles
land in the same cache backtests read, so recording also backfills chart history for free.

Later:

```python
run = ctx.backtest(strategy, ["AMD"], history_days=5, level1=True, level2=True)
```


## Going live

```python
ctx = Context(client)                        # paper (default)
ctx = Context(client, account_hash=...)      # real orders (account hash = account to place orders on)

session = ctx.deploy(strategy, ["AMD", "INTC"],
                    plot=True,             # live-streaming browser viewer
                    chart=True, level1=False, level2=False,
                    record=True)           # persist everything subscribed
```

* **Paper vs live** is decided when the `Trader` is constructed. Without `live_orders=True`
  nothing can ever leave the process, the session paper-trades the identical strategy on live data.
* **`cash`** defaults to your account's real settled cash when live (positions are adopted too, so
  `tc.sellable()` knows what you already own), or 10 000 for paper. Pass a number to override.
* **`record=True`** writes every subscribed data type to the DB through the same pipeline
  `record()` uses, feeding future backtests.
* Live fills, cancels and rejections arrive on Schwab's account-activity stream and are settled
  through the same accounting engine the backtester uses, so `tc.cash` / `tc.positions` stay
  consistent.

`session` is a `LiveContext`, also available as `trader.live`. Stop everything with
`trader.stop()`.


## The viewer

`run.serve()` / `plot=True` starts a local web server (first free port from 8000) and opens the
browser. One panel per ticker: close line, volume, your `tc.plots` overlays, and buy/sell markers
labelled with the executed quantity and price. The page polls once a second, so a running backtest
or live session streams in without refreshing.


## Notes and limits

* One `Data` store (one SQLite file) per `Trader`; pass `cache_db=` to keep separate universes.
* Minute-candle history is fetched in 10-day chunks at 2 requests/sec — the first pull of
  90 days × many tickers takes a few minutes; after that it's cached.
* Timestamps are UNIX ms everywhere; candles are stamped at the start of the minute they cover.
* Order rate limits (120/min, 4 000/day) are Schwab's, not enforced here.
* This module is in development. Use at your own risk especially with live orders.
