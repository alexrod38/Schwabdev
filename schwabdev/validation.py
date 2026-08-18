"""
Parameter Validation Module.
https://github.com/tylerebowers/Schwab-API-Python
"""
import datetime

_DATE_TYPES = (datetime.datetime, datetime.date, str)              # accepted by _time_convert
_NUMBER_TYPES = (int, float)                                       # bool excluded separately
_LIST_TYPES = (list, tuple, set, str)                              # accepted by _format_list

# Market data enums
_OPTION_CONTRACT_TYPES = frozenset({"CALL", "PUT", "ALL"})
_OPTION_STRATEGIES = frozenset({"SINGLE", "ANALYTICAL", "COVERED", "VERTICAL", "CALENDAR", "STRANGLE",
                                "STRADDLE", "BUTTERFLY", "CONDOR", "DIAGONAL", "COLLAR", "ROLL"})
_OPTION_EXP_MONTHS = frozenset({"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                "NOV", "DEC", "ALL"})
_OPTION_ENTITLEMENTS = frozenset({"PN", "NP", "PP"})
_QUOTE_FIELDS = frozenset({"all", "quote", "fundamental", "extended", "reference", "regular"})
_PERIOD_TYPES = frozenset({"day", "month", "year", "ytd"})
_FREQUENCY_TYPES = frozenset({"minute", "daily", "weekly", "monthly"})
# Valid period / frequency combinations from the price-history docs.
_VALID_PERIODS = {"day": {1, 2, 3, 4, 5, 10}, "month": {1, 2, 3, 6},
                  "year": {1, 2, 3, 5, 10, 15, 20}, "ytd": {1}}
_VALID_FREQ_TYPES = {"day": {"minute"}, "month": {"daily", "weekly"},
                     "year": {"daily", "weekly", "monthly"}, "ytd": {"daily", "weekly"}}
_VALID_FREQUENCIES = {"minute": {1, 5, 10, 15, 30}, "daily": {1}, "weekly": {1}, "monthly": {1}}
_MOVERS_SYMBOLS = frozenset({"$DJI", "$COMPX", "$SPX", "NYSE", "NASDAQ", "OTCBB", "INDEX_ALL",
                             "EQUITY_ALL", "OPTION_ALL", "OPTION_PUT", "OPTION_CALL"})
_MOVERS_SORTS = frozenset({"VOLUME", "TRADES", "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN"})
_MOVERS_FREQUENCIES = frozenset({0, 1, 5, 10, 30, 60})
_MARKETS = frozenset({"equity", "option", "bond", "future", "forex"})
_INSTRUMENT_PROJECTIONS = frozenset({"symbol-search", "symbol-regex", "desc-search", "desc-regex",
                                     "search", "fundamental"})
# Accounts & trading enums
_ORDER_STATUSES = frozenset({"AWAITING_PARENT_ORDER", "AWAITING_CONDITION", "AWAITING_STOP_CONDITION",
                             "AWAITING_MANUAL_REVIEW", "ACCEPTED", "AWAITING_UR_OUT", "PENDING_ACTIVATION",
                             "QUEUED", "WORKING", "REJECTED", "PENDING_CANCEL", "CANCELED", "PENDING_REPLACE",
                             "REPLACED", "FILLED", "EXPIRED", "NEW", "AWAITING_RELEASE_TIME",
                             "PENDING_ACKNOWLEDGEMENT", "PENDING_RECALL", "UNKNOWN"})
_TRANSACTION_TYPES = frozenset({"TRADE", "RECEIVE_AND_DELIVER", "DIVIDEND_OR_INTEREST", "ACH_RECEIPT",
                                "ACH_DISBURSEMENT", "CASH_RECEIPT", "CASH_DISBURSEMENT", "ELECTRONIC_FUND",
                                "WIRE_OUT", "WIRE_IN", "JOURNAL", "MEMORANDUM", "MARGIN_CALL", "MONEY_MARKET",
                                "SMA_ADJUSTMENT"})
_ACCOUNT_FIELDS = frozenset({"positions"})

class _Validator:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def _vtype(self, name, value, types, *, allow_none=True):
        if not self.enabled or (value is None and allow_none):
            return
        tt = types if isinstance(types, tuple) else (types,)
        names = " | ".join(t.__name__ for t in tt)
        if value is None:
            raise TypeError(f"{name} is required (expected {names}, got None)")
        if isinstance(value, bool) and bool not in tt:  # bool is a subclass of int; reject unless wanted
            raise TypeError(f"{name} must be {names} (got bool)")
        if not isinstance(value, tt):
            raise TypeError(f"{name} must be {names} (got {type(value).__name__})")

    def _vbool(self, name, value, *, allow_none=True):
        self._vtype(name, value, bool, allow_none=allow_none)

    def _vrange(self, name, value, lo=None, hi=None):
        if not self.enabled or value is None:
            return
        if lo is not None and value < lo:
            raise ValueError(f"{name} must be >= {lo} (got {value})")
        if hi is not None and value > hi:
            raise ValueError(f"{name} must be <= {hi} (got {value})")
        
    def _vhash(self, value):
        if not self.enabled or value is None:
            return
        if len(value) < 14:
            raise ValueError(f"accounthash failed length check, ensure using hashValue of account not accountNumber (client.linked_accounts())")


    def _vint(self, name, value, *, allow_none=True, lo=None, hi=None):
        self._vtype(name, value, int, allow_none=allow_none)
        self._vrange(name, value, lo, hi)

    def _vnum(self, name, value, *, allow_none=True, lo=None, hi=None):
        self._vtype(name, value, _NUMBER_TYPES, allow_none=allow_none)
        self._vrange(name, value, lo, hi)

    def _vdate(self, name, value, *, allow_none=True, allow_int=False):
        types = _DATE_TYPES + ((int,) if allow_int else ())
        self._vtype(name, value, types, allow_none=allow_none)

    def _vlist(self, name, value, *, allow_none=True):
        self._vtype(name, value, _LIST_TYPES, allow_none=allow_none)

    def _vin(self, name, value, allowed, *, allow_none=True):
        if not self.enabled or (value is None and allow_none):
            return
        if value not in allowed:
            raise ValueError(f"{name} must be one of {sorted(allowed, key=str)} (got {value!r})")

    def _vtokens(self, name, value, allowed, *, allow_none=True):
        """Validate each token of a comma-string or list/tuple/set against an allowed set."""
        if not self.enabled or (value is None and allow_none):
            return
        self._vlist(name, value, allow_none=allow_none)
        items = value.split(",") if isinstance(value, str) else value
        for item in items:
            token = item.strip() if isinstance(item, str) else item
            if token not in allowed:
                raise ValueError(f"{name} contains invalid value {token!r}; allowed: {sorted(allowed, key=str)}")

    # ---- per-endpoint validators (shared by Client and ClientAsync) -------- #
    def _v_account_details_all(self, fields):
        if not self.enabled:
            return
        self._vtokens("fields", fields, _ACCOUNT_FIELDS)

    def _v_account_details(self, accountHash, fields):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vtokens("fields", fields, _ACCOUNT_FIELDS)

    def _v_account_orders(self, accountHash, fromEnteredTime, toEnteredTime, maxResults, status):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vdate("fromEnteredTime", fromEnteredTime, allow_none=False)
        self._vdate("toEnteredTime", toEnteredTime, allow_none=False)
        self._vint("maxResults", maxResults, lo=1)
        self._vin("status", status, _ORDER_STATUSES)

    def _v_orders_all(self, fromEnteredTime, toEnteredTime, maxResults, status):
        if not self.enabled:
            return
        self._vdate("fromEnteredTime", fromEnteredTime, allow_none=False)
        self._vdate("toEnteredTime", toEnteredTime, allow_none=False)
        self._vint("maxResults", maxResults, lo=1)
        self._vin("status", status, _ORDER_STATUSES)

    def _v_order(self, accountHash, order):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vtype("order", order, dict, allow_none=False)

    def _v_order_id(self, accountHash, orderId):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vtype("orderId", orderId, (int, str), allow_none=False)

    def _v_replace_order(self, accountHash, orderId, order):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vtype("orderId", orderId, (int, str), allow_none=False)
        self._vtype("order", order, dict, allow_none=False)

    def _v_transactions(self, accountHash, startDate, endDate, types, symbol):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vdate("startDate", startDate, allow_none=False)
        self._vdate("endDate", endDate, allow_none=False)
        self._vin("types", types, _TRANSACTION_TYPES, allow_none=False)
        self._vtype("symbol", symbol, str)

    def _v_transaction_details(self, accountHash, transactionId):
        if not self.enabled:
            return
        self._vtype("accountHash", accountHash, str, allow_none=False)
        self._vhash(accountHash)
        self._vtype("transactionId", transactionId, (int, str), allow_none=False)

    def _v_quotes(self, symbols, fields, indicative):
        if not self.enabled:
            return
        self._vlist("symbols", symbols, allow_none=False)
        self._vtokens("fields", fields, _QUOTE_FIELDS)
        self._vbool("indicative", indicative)

    def _v_quote(self, symbol_id, fields):
        if not self.enabled:
            return
        self._vtype("symbol_id", symbol_id, str, allow_none=False)
        self._vtokens("fields", fields, _QUOTE_FIELDS)

    def _v_option_chains(self, symbol, contractType, strikeCount, includeUnderlyingQuote, strategy,
                         interval, strike, range_, fromDate, toDate, volatility, underlyingPrice,
                         interestRate, daysToExpiration, expMonth, optionType, entitlement):
        if not self.enabled:
            return
        self._vtype("symbol", symbol, str, allow_none=False)
        self._vin("contractType", contractType, _OPTION_CONTRACT_TYPES)
        self._vint("strikeCount", strikeCount, lo=1)
        self._vbool("includeUnderlyingQuote", includeUnderlyingQuote)
        self._vin("strategy", strategy, _OPTION_STRATEGIES)
        self._vtype("interval", interval, (int, float, str))  # declared str; API expects a number
        self._vnum("strike", strike)
        self._vtype("range", range_, str)
        self._vdate("fromDate", fromDate)
        self._vdate("toDate", toDate)
        self._vnum("volatility", volatility)
        self._vnum("underlyingPrice", underlyingPrice)
        self._vnum("interestRate", interestRate)
        self._vint("daysToExpiration", daysToExpiration, lo=0)
        self._vin("expMonth", expMonth, _OPTION_EXP_MONTHS)
        self._vtype("optionType", optionType, str)
        self._vin("entitlement", entitlement, _OPTION_ENTITLEMENTS)

    def _v_symbol(self, symbol):
        if not self.enabled:
            return
        self._vtype("symbol", symbol, str, allow_none=False)

    def _v_price_history(self, symbol, periodType, period, frequencyType, frequency,
                         startDate, endDate, needExtendedHoursData, needPreviousClose):
        if not self.enabled:
            return
        self._vtype("symbol", symbol, str, allow_none=False)
        self._vin("periodType", periodType, _PERIOD_TYPES)
        self._vint("period", period)
        self._vin("frequencyType", frequencyType, _FREQUENCY_TYPES)
        self._vint("frequency", frequency)
        self._vdate("startDate", startDate, allow_int=True)
        self._vdate("endDate", endDate, allow_int=True)
        self._vbool("needExtendedHoursData", needExtendedHoursData)
        self._vbool("needPreviousClose", needPreviousClose)
        # cross-parameter validity: period/frequency depend on periodType/frequencyType
        pint = int(period) if isinstance(period, str) and period.isdigit() else period
        if periodType in _VALID_PERIODS and isinstance(pint, int) and pint not in _VALID_PERIODS[periodType]:
            raise ValueError(f"period {pint} is invalid for periodType '{periodType}'; "
                             f"valid: {sorted(_VALID_PERIODS[periodType])}")
        if periodType in _VALID_FREQ_TYPES and frequencyType is not None and frequencyType not in _VALID_FREQ_TYPES[periodType]:
            raise ValueError(f"frequencyType '{frequencyType}' is invalid for periodType '{periodType}'; "
                             f"valid: {sorted(_VALID_FREQ_TYPES[periodType])}")
        if frequencyType in _VALID_FREQUENCIES and isinstance(frequency, int) and frequency not in _VALID_FREQUENCIES[frequencyType]:
            raise ValueError(f"frequency {frequency} is invalid for frequencyType '{frequencyType}'; "
                             f"valid: {sorted(_VALID_FREQUENCIES[frequencyType])}")

    def _v_movers(self, symbol, sort, frequency):
        if not self.enabled:
            return
        self._vin("symbol", symbol, _MOVERS_SYMBOLS, allow_none=False)
        self._vin("sort", sort, _MOVERS_SORTS)
        if frequency is not None:
            self._vtype("frequency", frequency, int)
            self._vin("frequency", frequency, _MOVERS_FREQUENCIES)

    def _v_market_hours(self, symbols, date):
        if not self.enabled:
            return
        self._vtokens("markets", symbols, _MARKETS, allow_none=False)
        self._vdate("date", date)

    def _v_market_hour(self, market_id, date):
        if not self.enabled:
            return
        self._vin("market_id", market_id, _MARKETS, allow_none=False)
        self._vdate("date", date)

    def _v_instruments(self, symbols, projection):
        if not self.enabled:
            return
        self._vlist("symbol(s)", symbols, allow_none=False)
        self._vin("projection", projection, _INSTRUMENT_PROJECTIONS, allow_none=False)

    def _v_cusip(self, cusip_id):
        if not self.enabled:
            return
        self._vtype("cusip_id", cusip_id, (int, str), allow_none=False)