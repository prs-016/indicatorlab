"""Adapt the existing Vibe Yahoo quoteSummary loader to India live quotes."""

from datetime import UTC, datetime

import requests


class YahooQuoteProvider:
    """Fetch one symbol per loader request, preserving Vibe's request pacing."""

    name = "yahoo"
    max_batch_size = 1

    def __init__(self, loader=None):
        if loader is None:
            from backtest.loaders.yahoo_client import get_quote_summary

            loader = get_quote_summary
        self.loader = loader

    def fetch(self, symbols):
        """Return Yahoo price, daily volume and exchange timestamp for one NSE name."""
        (symbol,) = symbols
        try:
            response = self.loader(symbol, ["price"])
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status in (401, 403, 429):
                raise PermissionError("Yahoo rejected or rate-limited access") from None
            if status is not None and status < 500:
                raise ValueError("Yahoo rejected the quote request") from None
            raise

        price = response.get("price", {})

        def raw(key):
            value = price.get(key)
            return value.get("raw") if isinstance(value, dict) else value

        if price.get("symbol") != symbol or price.get("currency") != "INR":
            raise ValueError("Unexpected Yahoo quote identity or currency")
        change = price.get("regularMarketChangePercent")
        # Yahoo's formatted value explicitly carries percent units.
        percent = change.get("fmt") if isinstance(change, dict) else None
        if not isinstance(percent, str) or not percent.endswith("%"):
            raise ValueError("Missing Yahoo percent units")
        timestamp = raw("regularMarketTime")
        if type(timestamp) not in (int, float):
            raise ValueError("Invalid Yahoo exchange timestamp")
        return {
            symbol: {
                "symbol": symbol,
                "price": raw("regularMarketPrice"),
                "change_pct": float(percent[:-1]),
                "volume": raw("regularMarketVolume"),
                "ts_exchange": datetime.fromtimestamp(timestamp, UTC),
                "source": self.name,
            }
        }
