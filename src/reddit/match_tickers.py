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

from src import config
from src.reddit import settings
from src.reddit.utils import get_logger

log = get_logger("match_tickers", "pipeline.log")

B = r"(?<![A-Za-z0-9_$])"   # left boundary that also rejects "$" (cashtags handled separately)
E = r"(?![A-Za-z0-9_])"     # right boundary

URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|net|org|io|co)(?:/\S*)?)", re.I)
REMOVED = {"[removed]", "[deleted]", "[removed by reddit]"}

@dataclass
class _Compiled:
    cashtag: re.Pattern
    ticker: re.Pattern
    names: list[re.Pattern]
    ambiguous_name: str | None = None
    # Optional context rule for a name that is ambiguous on its own (e.g. capitalised "Meta").
    ctx_word: re.Pattern | None = None
    ctx_strong: re.Pattern | None = None
    ctx_terms: re.Pattern | None = None


def compile_market(market: str) -> dict[str, _Compiled]:
    """Compile the cashtag, ticker and company-name patterns of every stock in `market` from config.yaml."""
    out: dict[str, _Compiled] = {}
    for tk, cfg in config.stocks(market).items():
        m = cfg["match"]
        alt = "|".join(m["symbols"])
        names = [re.compile(B + n["pattern"] + E, re.I if n.get("ignore_case") else 0) for n in m.get("names", [])]
        c = _Compiled(cashtag=re.compile(r"(?<![A-Za-z0-9_$])\$(?:" + alt + r")" + E, re.I),
                      ticker=re.compile(B + r"(?:" + alt + r")" + E), names=names,
                      ambiguous_name=m.get("ambiguous_name"))
        ctx = m.get("contextual_name")
        if ctx:
            c.ctx_word = re.compile(B + ctx["word"] + E)
            c.ctx_strong = re.compile(B + ctx["strong"], re.I)
            c.ctx_terms = re.compile(r"\b(?:" + "|".join(ctx["context_terms"]) + r")\b")
        out[tk] = c
    return out


COMPILED = compile_market(settings.MARKET)

METHOD_ORDER = ["cashtag", "ticker", "company_name"]


def clean_text(s) -> str:
    if not isinstance(s, str) or s.strip().lower() in REMOVED:
        return ""
    return URL_RE.sub(" ", html.unescape(s))


def _contextual_name(c: _Compiled, text: str, context: str) -> re.Match | None:
    """The ambiguous capitalised name in `text` when it refers to the company; `context` is the whole post."""
    for m in c.ctx_word.finditer(text):
        if c.ctx_strong.match(text, m.start()):
            return m
    m = c.ctx_word.search(text)
    if m and c.ctx_terms.search(context):
        return m
    return None


def match_text(text: str, context: str | None = None) -> dict[str, dict[str, str]]:
    """Return {ticker: {method: first matched string}} for one cleaned text.

    `context` (default: `text`) is the full post, used only by context rules (META's "Meta").
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
        if c.ctx_word is not None and "company_name" not in hits:
            m = _contextual_name(c, text, context)
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
            "ambiguous_term": best == "company_name" and COMPILED[tk].ambiguous_name is not None
                              and methods[best].lower().startswith(COMPILED[tk].ambiguous_name.lower()),
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
