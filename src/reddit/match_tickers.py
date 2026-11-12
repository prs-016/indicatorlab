"""Match Reddit posts (title + selftext) to the tracked stocks in config.yaml.

How a post is matched depends on its subreddit's type (config.yaml):
  product          every post counts for the subreddit's company (method `subreddit`):
                   r/iphone is Apple by definition
  stock, general,  text matching below; a post may match several stocks
  sector

Three text-match methods, strongest first:
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
  * Signature and disclosure lines ("Positions: AAPL, MSFT", "Disclosure: long NVDA")
    are stripped before matching, so a user's standing holdings are not mentions.
  * `multi_ticker_list` flags posts that text-match MULTI_TICKER_LIST_MIN or more tracked
    stocks (watch lists, "Mag 7" round-ups); they are kept, and analyses can drop them.

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
from src.reddit.utils import REMOVED_TEXT, get_logger

log = get_logger("match_tickers", "pipeline.log")

B = r"(?<![A-Za-z0-9_$])"   # left boundary that also rejects "$" (cashtags handled separately)
E = r"(?![A-Za-z0-9_])"     # right boundary

# A line that starts (after list/quote/bold markers) with Positions:/Disclosure:/Holdings:.
SIGNATURE_RE = re.compile(r"^[\s>*_#-]*(?:my |current )?(?:positions?|disclosures?|holdings?)\s*:.*$",
                          re.I | re.M)
MULTI_TICKER_LIST_MIN = config.load()["reddit"]["multi_ticker_list_min"]
URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|net|org|io|co)(?:/\S*)?)", re.I)

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
    """Post text ready for matching: unescaped, without URLs and signature lines; "" if removed."""
    if not isinstance(s, str) or s.strip().lower() in REMOVED_TEXT:
        return ""
    return SIGNATURE_RE.sub(" ", URL_RE.sub(" ", html.unescape(s)))


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


POST_COLS = ["id", "subreddit", "subreddit_type", "owner_ticker", "market", "created_utc", "created_dt", "date",
             "title", "selftext", "score", "num_comments", "permalink", "day_status", "removed_by_category",
             "removed_flag", "period"]
OUT_COLS = ["post_id", "market", "subreddit", "subreddit_type", "created_utc", "created_utc_iso", "date", "period",
            "ticker", "match_method", "all_methods", "matched_text", "found_in", "ambiguous_term", "n_tickers_in_post",
            "multi_ticker_list", "score", "num_comments", "permalink", "day_status", "removed_by_category",
            "removed_flag"]


def match_subreddit(posts: pd.DataFrame) -> pd.DataFrame:
    """Match rows for the posts of one subreddit (all rows share one subreddit type)."""
    kind = posts["subreddit_type"].iloc[0]
    if kind == "product":
        m = pd.DataFrame({"post_id": posts["id"].to_numpy(), "ticker": posts["owner_ticker"].to_numpy(),
                          "match_method": "subreddit", "all_methods": "subreddit", "matched_text": "",
                          "found_in": "subreddit", "ambiguous_term": False, "n_tickers_in_post": 0})
    else:
        out = []
        for r in posts[["id", "title", "selftext"]].itertuples(index=False):
            hits = match_post(r.title, r.selftext)
            for h in hits:
                h["post_id"] = r.id
                h["n_tickers_in_post"] = len(hits)
            out.extend(hits)
        m = pd.DataFrame(out, columns=["ticker", "match_method", "all_methods", "matched_text", "found_in",
                                       "ambiguous_term", "post_id", "n_tickers_in_post"])
    m["multi_ticker_list"] = m["n_tickers_in_post"] >= MULTI_TICKER_LIST_MIN
    meta = posts.drop(columns=["title", "selftext", "owner_ticker"]).rename(columns={"id": "post_id"})
    df = m.merge(meta, on="post_id", how="left")
    df["created_utc_iso"] = df["created_dt"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df[OUT_COLS]


def run() -> pd.DataFrame:
    """Match every subreddit file and write post_ticker_matches.parquet (no post text; join it when needed)."""
    parts = []
    for f in sorted(settings.POSTS.glob("*.parquet")):
        posts = pd.read_parquet(f, columns=POST_COLS)
        if posts.empty:
            continue
        parts.append(match_subreddit(posts))
        log.info("r/%s (%s): %d posts -> %d match rows", posts["subreddit"].iloc[0], posts["subreddit_type"].iloc[0],
                 len(posts), len(parts[-1]))
    df = pd.concat(parts, ignore_index=True).sort_values(["created_utc", "post_id", "ticker"])
    dup = df.duplicated(["post_id", "ticker"]).sum()
    assert dup == 0, f"{dup} duplicate post/ticker rows"
    df.to_parquet(settings.PROCESSED / "post_ticker_matches.parquet", index=False)
    methods = ["subreddit", *METHOD_ORDER]
    summary = (df.groupby(["market", "subreddit_type", "ticker", "match_method"]).size().unstack(fill_value=0)
               .reindex(columns=methods, fill_value=0))
    summary.columns = [f"{m}_posts" for m in methods]   # avoid a 'ticker' column clashing with the index
    summary["total_posts"] = summary.sum(axis=1)
    summary["multi_ticker_list_posts"] = df.groupby(["market", "subreddit_type", "ticker"])["multi_ticker_list"].sum()
    summary.to_csv(settings.TABLES / "match_method_summary.csv")
    log.info("matched rows=%d unique posts=%d", len(df), df["post_id"].nunique())
    return df


if __name__ == "__main__":
    run()
