"""NSE and BSE symbol normalization and local metadata for the shared resolver."""

import csv
import re
from functools import cache
from pathlib import Path

from src.india_wikipedia_mapping import load_india_titles
from src.markets.errors import SymbolLookupUnavailable, UnknownTicker

_ROSTER = Path(__file__).resolve().parents[2] / "config/india_wiki_coverage.csv"
_TICKER = re.compile(r"(?:(NSE|BSE):)?([A-Z0-9][A-Z0-9&-]{0,19})(?:\.(NS|BO))?")
_COMPANY_SUFFIX = re.compile(r"\s+(?:Ltd\.?|Limited)$", re.IGNORECASE)
_HISTORY_TIMEOUT_SECONDS = 5
_NIFTY_100_COUNT = 100
INDIA_AMBIGUOUS = frozenset(
    {"Titan", "Trent", "Hero", "Max", "Eternal", "Bharat", "Indus", "Bank"}
)
# First entry is the display name. The others are reviewed common or former names.
_ALIASES = {
    "RELIANCE": ("Reliance", "RIL"),
    "INFY": ("Infosys",),
    "HDFCBANK": ("HDFC Bank",),
    "TCS": ("TCS", "Tata Consultancy"),
    "ETERNAL": ("Eternal", "Zomato"),
    "TITAN": ("Titan",),
    "TRENT": ("Trent",),
    "MAXHEALTH": ("Max Healthcare", "Max"),
    "BEL": ("Bharat Electronics", "Bharat"),
    "BHARTIARTL": ("Bharti Airtel", "Airtel"),
    "SBIN": ("State Bank of India", "SBI"),
    "M&M": ("Mahindra & Mahindra", "Mahindra"),
    "HINDUNILVR": ("Hindustan Unilever", "HUL"),
    "LT": ("Larsen & Toubro", "L&T"),
    "BAJAJ-AUTO": ("Bajaj Auto",),
}

# Populated only with communities for which the checked 2026 witness exists.
INDIA_SUBREDDITS = (
    "IndianStockMarket",
    "IndiaInvestments",
    "IndianStreetBets",
)


@cache
def _roster_names() -> dict[str, str]:
    with _ROSTER.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    names = {row["symbol"] + ".NS": row["company_name"] for row in rows}
    if (
        len(rows) != _NIFTY_100_COUNT
        or len(names) != len(rows)
        or not all(names.values())
    ):
        raise ValueError("Expected 100 distinct NIFTY company names")
    return names


def india_names(*, include_parent_proxies: bool = False) -> dict[str, dict]:
    """Return an independent metadata mapping keyed by tracked .NS symbols.

    By default, titles identify the listed company. Set include_parent_proxies
    to also return approved English parent titles. Unresolved titles stay None.
    Untracked stocks have no local entry.
    """
    titles = load_india_titles().current_titles(
        include_parent_proxies=include_parent_proxies
    )
    names = {}
    ambiguous_aliases = {name.casefold() for name in INDIA_AMBIGUOUS}
    for ticker, company in _roster_names().items():
        bare = ticker.removesuffix(".NS")
        short = _COMPANY_SUFFIX.sub("", company)
        aliases = _ALIASES.get(bare, (short,))
        wiki = titles.get(ticker, {})
        names[ticker] = {
            "name": company,
            "short_name": aliases[0],
            "aliases": list(aliases),
            "ambiguous": any(
                alias.casefold() in ambiguous_aliases for alias in aliases
            ),
            "wiki_en": wiki.get("en"),
            "wiki_hi": wiki.get("hi"),
        }
    return names


def _history_exists(symbol: str) -> bool:
    import yfinance as yf
    from yfinance.exceptions import YFTickerMissingError

    try:
        history = yf.Ticker(symbol).history(
            period="1mo",
            interval="1d",
            timeout=_HISTORY_TIMEOUT_SECONDS,
            raise_errors=True,
        )
        return not history.empty and bool(history["Close"].dropna().gt(0).any())
    except YFTickerMissingError:
        return False
    except Exception as error:
        raise SymbolLookupUnavailable(
            f"Price history lookup unavailable for {symbol}"
        ) from error


def _company_name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _COMPANY_SUFFIX.sub("", name.strip()).casefold())


def _nse_equivalent(bse_symbol: str) -> str | None:
    import yfinance as yf

    try:
        info = yf.Ticker(bse_symbol).get_info()
        name = info.get("longName") or info.get("shortName")
        if not isinstance(name, str) or not _company_name_key(name):
            return None
        identity = _company_name_key(name)
        candidates = {
            symbol
            for symbol, company in _roster_names().items()
            if _company_name_key(company) == identity
        }
        if not candidates:
            matches = yf.Search(
                name,
                max_results=8,
                news_count=0,
                lists_count=0,
                recommended=0,
                timeout=_HISTORY_TIMEOUT_SECONDS,
            ).quotes
            for match in matches:
                symbol = match.get("symbol", "")
                names = (match.get("longname"), match.get("shortname"))
                if (
                    isinstance(symbol, str)
                    and symbol.endswith(".NS")
                    and any(
                        isinstance(n, str) and _company_name_key(n) == identity
                        for n in names
                    )
                ):
                    candidates.add(symbol)
    except Exception as error:
        raise SymbolLookupUnavailable(
            f"Company lookup unavailable for {bse_symbol}"
        ) from error
    if len(candidates) == 1:
        candidate = next(iter(candidates))
        if _history_exists(candidate):
            return candidate
    return None


def normalize_in(raw: str) -> str:
    """Resolve an India ticker to its confirmed yfinance symbol.

    Known NSE constituents resolve locally. Named BSE tickers prefer the matching
    NSE symbol if history exists. Six-digit BSE codes resolve by company identity
    when a unique NSE counterpart has history. UnknownTicker denotes invalid or
    unlisted input. SymbolLookupUnavailable denotes a failed provider lookup.
    """
    value = raw.strip().removeprefix("$").upper() if isinstance(raw, str) else ""
    match = _TICKER.fullmatch(value)
    if match is None:
        raise UnknownTicker(f"Invalid India ticker: {raw!r}")
    exchange, bare, suffix = match.groups()
    numeric = bare.isdecimal()
    if (
        (numeric and (len(bare) != 6 or exchange == "NSE" or suffix == "NS"))
        or (exchange == "NSE" and suffix == "BO")
        or (exchange == "BSE" and suffix == "NS")
    ):
        raise UnknownTicker(f"Invalid India ticker: {raw!r}")
    nse = bare + ".NS"
    bse = bare + ".BO"
    if numeric:
        if _history_exists(bse):
            return _nse_equivalent(bse) or bse
    elif exchange == "BSE" or suffix == "BO":
        if _history_exists(nse):
            return nse
        if _history_exists(bse):
            return bse
    elif nse in _roster_names() or _history_exists(nse):
        return nse
    raise UnknownTicker(f"No India price history for {raw!r}")
