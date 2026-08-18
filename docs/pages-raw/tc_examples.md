### You can find all examples in the `/docs/examples/` folder of the Schwabdev-Context repository <a target="_blank" href="https://github.com/tylerebowers/Schwabdev-Context/tree/main/docs/examples">here</a>.


## Main Examples

### Simple Moving Average Example Strategy

```python
from schwabdev import Context, Client

client = Client(...) # fill in client info as normal
tickers = ["MSFT", "NVDA", "AAPL", "GOOGL", "META", "AMZN", "TSLA", "MSTR", "AMD", "INTC", "AMAT", "ASML", "LRCX"]

def order(symbol, instruction, quantity): # shortcut to make orders
    """A minimal Schwab MARKET order dict."""
    return {"orderType": "MARKET", "session": "NORMAL", "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{"instruction": instruction, "quantity": quantity,
                                    "instrument": {"symbol": symbol, "assetType": "EQUITY"}}]}


class sma_Strategy: # Simple Moving Average Strategy
    def __init__(self, tickers, fast=100, slow=400, slice_pct=0.10):  # windows in minute bars
        self.fast, self.slow = fast, slow
        self.slice_pct = slice_pct          # fraction of cash to spend per buy signal

    def __call__(self, tc, events):
        for e in events:
            if e["type"] != "c":  # act on candles only
                continue
            sym = e["symbol"] # get the symbol that the candle applies to
            closes = [c["close"] for c in tc.candles[sym]] # get the close prices
            if len(closes) <= self.slow: # not enough history for the slow SMA yet
                continue

            sma = lambda n, end: sum(closes[end - n:end]) / n
            fast_now,  slow_now  = sma(self.fast, len(closes)),     sma(self.slow, len(closes))
            fast_prev, slow_prev = sma(self.fast, len(closes) - 1), sma(self.slow, len(closes) - 1)
            tc.plots.setdefault(f"sma{self.fast} {sym}", []).append((e["time"], fast_now))
            tc.plots.setdefault(f"sma{self.slow} {sym}", []).append((e["time"], slow_now))

            price = closes[-1]
            if fast_prev <= slow_prev and fast_now > slow_now:      # crossed up -> buy a slice
                qty = int(tc.cash * self.slice_pct / price)
                if qty > 0:
                    tc.order(order(sym, "BUY", qty))
            elif fast_prev >= slow_prev and fast_now < slow_now:    # crossed down -> exit
                qty = int(tc.sellable(sym))
                if qty > 0:
                    tc.order(order(sym, "SELL", qty))


tc = Context(client)
strat = sma_Strategy(tickers=tickers)
run = tc.backtest(strat, tickers=tickers, cash=10_000, history_days=60, plot=True)
```

To run this strategy on live data we can make this change on the last line:

```python
run = tc.deploy(strat, tickers=tickers, cash=10_000, plot=True)
```

Then to allow placing orders we must specify an account hash to trade on:
(please not that the provided strategy is NOT profitable)

```python
client = Client(...)
hash = client.linked_accounts().json()[0]["hashValue"] # get the first account hash
tickers = ["AMD"]
# above the strategy ^

# it is recommend to only allow buying/selling of 1 unit at a time when first testing.
# in __call__ we can change this as needed:
if fast_prev <= slow_prev and fast_now > slow_now: 
    tc.order(order(sym, "BUY", 1))
elif fast_prev >= slow_prev and fast_now < slow_now: 
    qty = int(tc.sellable(sym))
    if qty > 0:
        tc.order(order(sym, "SELL", 1))

# below the strategy:
tc = Context(client, account_hash=hash)
strat = sma_Strategy(tickers=tickers)
run = tc.deploy(strat, tickers=tickers, cash=1_000, plot=True)
```