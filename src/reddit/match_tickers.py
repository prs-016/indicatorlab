"""Match Reddit posts (title + selftext) to the 10 tracked stocks.

Three match methods, strongest first:
  cashtag       $AAPL, $aapl            (case-insensitive)
  ticker        AAPL as a whole word    (case-sensitive, upper-case only)
  company_name  Apple, Microsoft, ...   (curated aliases with exclusions)

Ambiguity handling (see also tests/test_matching.py):
  * URLs are stripped first (amazon.com / google.com links are not mentions).
  * META: lower-case "meta" never matches. Upper-case META counts as a ticker.
    Capitalised "Meta" counts only with company context: "Meta's", "Meta Platforms",
    a nearby stock word (stock/shares/earnings/calls/puts/...), or company-specific
    terms anywhere in the post (Zuckerberg, Facebook, Instagram, WhatsApp, ...).
    "Meta-analysis" and "meta thread"-style uses are excluded.
  * AMD only upper-case; Apple / Amazon / Alphabet only capitalised or all-caps
    (so fruit, river, and the word "alphabet" are skipped), with phrase exclusions
    such as "Big Apple", "Apple Hospitality", "Amazon rainforest", "Nikola Tesla".
  * GOOG (class C) is accepted as a ticker for Alphabet (GOOGL). "Google it" is excluded.
  * "Chase" alone is not matched; only J.P. Morgan variants and "Chase Bank".

A post contributes at most one row per ticker; `match_method` holds the strongest
method found, `all_methods` every method that fired.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

import pandas as pd

from src.reddit import settings
from src.reddit.utils import get_logger

log = get_logger("match_tickers", "pipeline.log")

B = r"(?<![A-Za-z0-9_$])"   # left boundary that also rejects "$" (cashtags handled separately)
E = r"(?![A-Za-z0-9_])"     # right boundary

URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|net|org|io|co)(?:/\S*)?)", re.I)
REMOVED = {"[removed]", "[deleted]", "[removed by reddit]"}

TICKER_SYMBOLS = {t: [t] for t in settings.TICKERS}
TICKER_SYMBOLS["GOOGL"] = ["GOOGL", "GOOG"]

# Company-name aliases: (pattern, flags). Patterns are wrapped with word boundaries.
NAME_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "AAPL": [(r"(?<!Big )(?<!BIG )(?:Apple|APPLE)(?! Hospitality)(?! Bank)(?! HOSPITALITY)", 0)],
    "MSFT": [(r"Microsoft", re.I)],
    "NVDA": [(r"Nvidia", re.I)],
    "TSLA": [(r"(?<!Nikola )Tesla", re.I)],
    "AMZN": [(r"(?:Amazon|AMAZON)(?! [Rr]ainforest)(?! [Rr]iver)(?! [Bb]asin)(?! [Jj]ungle)", 0)],
    "META": [(r"Meta Platforms", re.I), (r"Facebook", re.I)],   # contextual "Meta" handled in code
    "GOOGL": [(r"Google(?! it\b)(?! that\b)(?! this\b)", re.I), (r"(?:Alphabet|ALPHABET)", 0)],
    "AMD": [(r"Advanced Micro Devices", re.I)],
    "NFLX": [(r"Netflix", re.I)],
    "JPM": [(r"J\.?\s?P\.?\s?Morgan", re.I), (r"Chase Bank", re.I)],
}

# Terms that are ambiguous on their own; recorded for validation sampling.
AMBIGUOUS_NAMES = {"AAPL": "Apple", "AMZN": "Amazon", "META": "Meta", "GOOGL": "Alphabet"}

META_CAP_RE = re.compile(B + r"Meta(?!-)(?! [Tt]hread)(?! [Pp]ost)(?! [Aa]nalysis)" + E)
META_STRONG_RE = re.compile(B + r"Meta(?:'s|’s| Platforms" +
                            r"|\s+(?:\w+\s+){0,2}?(?:stock|stocks|shares|earnings|calls|puts|options|price|PT|ER|guidance|capex)\b)", re.I)
META_CONTEXT_RE = re.compile(r"\b(?:Zuckerberg|Zuck|Facebook|Instagram|WhatsApp|Oculus|Reality Labs|Llama|"
                             r"Threads app|FAANG|MAANG|Mag(?:nificent)? ?7|Magnificent Seven|big tech|"
                             r"Apple|Microsoft|Google|Alphabet|Amazon|Nvidia|Netflix|Tesla|"
                             r"AAPL|MSFT|GOOGL?|AMZN|NVDA|NFLX|TSLA|\$META|META)\b")


@dataclass
class _Compiled:
    cashtag: re.Pattern
    ticker: re.Pattern
    names: list[re.Pattern]


COMPILED: dict[str, _Compiled] = {}
for _t, _syms in TICKER_SYMBOLS.items():
    alt = "|".join(_syms)
    COMPILED[_t] = _Compiled(
        cashtag=re.compile(r"(?<![A-Za-z0-9_$])\$(?:" + alt + r")" + E, re.I),
        ticker=re.compile(B + r"(?:" + alt + r")" + E),
        names=[re.compile(B + p + E, f) for p, f in NAME_PATTERNS[_t]],
    )

METHOD_ORDER = ["cashtag", "ticker", "company_name"]


def clean_text(s) -> str:
    if not isinstance(s, str) or s.strip().lower() in REMOVED:
        return ""
    return URL_RE.sub(" ", html.unescape(s))


def _meta_contextual(text: str, context: str) -> re.Match | None:
    """Capitalised 'Meta' in `text` that refers to the company; `context` is the whole post."""
    for m in META_CAP_RE.finditer(text):
        if META_STRONG_RE.match(text, m.start()):
            return m
    m = META_CAP_RE.search(text)
    if m and META_CONTEXT_RE.search(context):
        return m
    return None


def match_text(text: str, context: str | None = None) -> dict[str, dict[str, str]]:
    """Return {ticker: {method: first matched string}} for one cleaned text.

    `context` (default: `text`) is the full post, used only for META's company-context rule.
    """
    context = text if context is None else context
    out: dict[str, dict[str, str]] = {}
    for t, c in COMPILED.items():
        hits: dict[str, str] = {}
        m = c.cashtag.search(text)
        if m:
            hits["cashtag"] = m.group(0)
        m = c.ticker.search(text)
        if m:
            hits["ticker"] = m.group(0)
        for p in c.names:
            m = p.search(text)
            if m:
                hits["company_name"] = m.group(0)
                break
        if t == "META" and "company_name" not in hits:
            m = _meta_contextual(text, context)
            if m:
                hits["company_name"] = m.group(0)
        if hits:
            out[t] = hits
    return out


def match_post(title: str, selftext: str) -> list[dict]:
    """One dict per matched ticker for a post (title and body are both searched)."""
    t_clean, b_clean = clean_text(title), clean_text(selftext)
    full = t_clean + "\n" + b_clean
    in_title, in_body = match_text(t_clean, full), match_text(b_clean, full)
    rows = []
    for tk in sorted(set(in_title) | set(in_body)):
        methods = {**in_body.get(tk, {}), **in_title.get(tk, {})}   # title text wins for display
        best = next(m for m in METHOD_ORDER if m in methods)
        where = "both" if tk in in_title and tk in in_body else ("title" if tk in in_title else "body")
        rows.append({
            "ticker": tk,
            "match_method": best,
            "all_methods": ";".join(m for m in METHOD_ORDER if m in methods),
            "matched_text": methods[best],
            "found_in": where,
            "ambiguous_term": best == "company_name" and tk in AMBIGUOUS_NAMES
                              and methods[best].lower().startswith(AMBIGUOUS_NAMES[tk].lower()),
        })
    return rows


def run() -> pd.DataFrame:
    posts = pd.read_parquet(settings.PROCESSED / "posts.parquet")
    log.info("matching %d posts", len(posts))
    out = []
    for r in posts[["id", "title", "selftext"]].itertuples(index=False):
        for m in match_post(r.title, r.selftext):
            m["post_id"] = r.id
            out.append(m)
    mt = pd.DataFrame(out)
    cols = ["id", "subreddit", "created_utc", "created_dt", "date", "title", "selftext", "score",
            "num_comments", "permalink", "day_status", "removed_by_category"]
    df = mt.merge(posts[cols].rename(columns={"id": "post_id"}), on="post_id", how="left")
    df["created_utc_iso"] = df["created_dt"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    dup = df.duplicated(["post_id", "ticker"]).sum()
    assert dup == 0, f"{dup} duplicate post/ticker rows"
    df = df[["post_id", "subreddit", "created_utc", "created_utc_iso", "date", "ticker", "match_method",
             "all_methods", "matched_text", "found_in", "ambiguous_term", "title", "selftext", "score",
             "num_comments", "permalink", "day_status", "removed_by_category"]].sort_values(["created_utc", "post_id", "ticker"])
    df.to_parquet(settings.PROCESSED / "post_ticker_matches.parquet", index=False)
    df.to_csv(settings.PROCESSED / "post_ticker_matches.csv", index=False)
    summary = (df.groupby(["ticker", "match_method"]).size().unstack(fill_value=0)
               .reindex(columns=METHOD_ORDER, fill_value=0))
    summary.columns = [f"{m}_posts" for m in METHOD_ORDER]   # avoid a 'ticker' column clashing with the index
    summary["total_posts"] = summary.sum(axis=1)
    summary.to_csv(settings.TABLES / "match_method_summary.csv")
    log.info("matched rows=%d unique posts=%d\n%s", len(df), df["post_id"].nunique(), summary)
    log.info("found_in counts: %s", df["found_in"].value_counts().to_dict())
    return df


if __name__ == "__main__":
    run()
