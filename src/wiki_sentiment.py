"""Sentiment of the text editors add to a stock's Wikipedia article, scored by a Hugging Face model.

Edit summaries are mostly bookkeeping ("ce", "add link"; 73% neutral under VADER), so this scores the
article text itself. For each week it takes the net change from the revision live at the start of the
week (Monday 00:00 UTC) to the one live at its end, so vandalism reverted within the week drops out.
Only new or changed sentences are scored, by Joshua's FinBERT scorer shared with Reddit
(src/sentiment/finbert_scorer.py: ProsusAI/finbert pinned in config.yaml `sentiment`), so both sources
report the same columns: sentiment_pos, sentiment_neg, sentiment_neu and sentiment_net = pos - neg.

    python -m src.wiki_sentiment            # tracked stocks, research period: fetch, score, then `analyse`
    python -m src.wiki_sentiment analyse    # only the returns tests, from the saved scores
    python -m src.wiki_sentiment strategy   # all strategy-universe stocks (Week 3 S4), *_research_strategy.csv
"""
import html
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.sentiment.finbert_scorer import (
    FinbertScorer,
    ScoreCache,
    prepare_text,
    score_items,
    text_sha1,
)
from src.wiki_attention import ACTION_API_URL, REQUEST_TIMEOUT_S, SESSION, user_agent

INS, END = "\x01", "\x02"   # mark inserted text so it survives the wikitext clean-up
ADDED_CELL = re.compile(r'<td class="diff-addedline[^"]*">(.*?)</td>', re.DOTALL)
TABLE_LINE = re.compile(r"^\s*(?:[|!]|\{\||\|\})")   # infobox fields and table rows are not prose
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\x01\x02])")
DOT = "\x03"                # a full stop that does not end a sentence: "U.S.", "Inc.", "Lawrence E. Page"
ABBREV = re.compile(r"\b(?:[A-Z]|Inc|Corp|Co|Ltd|Jr|Sr|Mr|Mrs|Ms|Dr|St|vs|No)\.")
YEAR = re.compile(r"\b(?:19[5-9]\d|20[0-4]\d)\b")
CHECKPOINT_WEEKS = 50       # save the diff cache this often, so an interrupted run loses little
STALE_YEARS = 2             # a sentence whose latest year is this much older than its week is old history


def params() -> dict:
    """The `wikipedia.sentiment` block of config.yaml."""
    return config.load()["wikipedia"]["sentiment"]


def week_pairs(revs: pd.DataFrame, weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """For each week with edits: the revision live when it starts (`from_rev`) and when it ends (`to_rev`).

    `revs` needs `revid` and naive-UTC `timestamp` and must include the last revision before the first week.
    Weeks with no edits, or with no earlier revision to compare against, are left out.
    """
    r = revs.sort_values("timestamp")
    ts, ids = r["timestamp"].to_numpy(), r["revid"].to_numpy()
    rows = []
    for w in weeks:
        i = np.searchsorted(ts, np.datetime64(w), "left") - 1
        j = np.searchsorted(ts, np.datetime64(w + pd.Timedelta(days=7)), "left") - 1
        if i >= 0 and j > i:
            rows.append({"week": w, "from_rev": int(ids[i]), "to_rev": int(ids[j])})
    return pd.DataFrame(rows, columns=["week", "from_rev", "to_rev"])


def compare(from_rev: int, to_rev: int, lang: str = "en") -> str:
    """HTML diff table between two revisions (MediaWiki action=compare); '' if a revision is hidden."""
    q = {"action": "compare", "fromrev": from_rev, "torev": to_rev, "prop": "diff",
         "format": "json", "formatversion": 2}
    r = SESSION.get(ACTION_API_URL.format(lang=lang), params=q, headers=user_agent(), timeout=REQUEST_TIMEOUT_S)
    r.raise_for_status()
    return r.json().get("compare", {}).get("body", "")


def clean_wikitext(text: str) -> str:
    """Plain text from one line of wikitext: drops refs, templates, comments, files and markup."""
    t = re.sub(r"<ref[^>]*/>", "", text)
    t = re.sub(r"<ref[^>]*>.*?(?:</ref>|$)", "", t)          # also a ref left open at the line end
    t = re.sub(r"<!--.*?(?:-->|$)", "", t)
    prev = None
    while prev != t:                                         # innermost templates first
        prev, t = t, re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:File|Image|Category):[^\]]*\]\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)  # [[target|label]] -> label
    t = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", t)     # [url label] -> label
    t = re.sub(r"<[^>]+>|'{2,}|={2,}|^[*#:;]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def added_sentences(diff_html: str, min_words: int = 5) -> list[str]:
    """Sentences that a diff adds or changes, as plain text.

    A wholly new line keeps all its sentences; a changed line keeps only sentences touching the
    inserted words. Moved paragraphs, tables and infobox fields are skipped.
    """
    out = []
    for cell in ADDED_CELL.findall(diff_html):
        if "mw-diff-movedpara" in cell:
            continue
        changed_line = "<ins" in cell
        text = re.sub(r"<ins[^>]*>", INS, cell).replace("</ins>", END)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        if TABLE_LINE.match(text.lstrip(INS + END)):
            continue
        inside = False
        # "here.</ins> Next": put the marker before the full stop, so the split keeps it in its sentence
        text = re.sub(r"([.!?])([\x01\x02]+)", r"\2\1", clean_wikitext(text))
        text = ABBREV.sub(lambda m: m.group().replace(".", DOT), text)
        for s in SENTENCE_END.split(text):
            touched = inside or INS in s or END in s
            if INS in s or END in s:
                inside = s.rfind(INS) > s.rfind(END)
            s = s.replace(INS, "").replace(END, "").replace(DOT, ".").strip()
            if (touched or not changed_line) and len(s.split()) >= min_words and re.search("[A-Za-z]", s):
                out.append(s)
    return out


def week_sentences(ticker: str, revs: pd.DataFrame, weeks: pd.DatetimeIndex, cache_file: Path,
                   lang: str = "en", seed_file: Path | None = None) -> pd.DataFrame:
    """Added sentences per week (one row per sentence; '' for a week that added none), cached per article.

    The cache is saved every CHECKPOINT_WEEKS fetched weeks, so an interrupted run resumes: weeks already
    in `cache_file` are not fetched again. A new `cache_file` starts from `seed_file` (an earlier cutoff's
    cache, only read), keeping the weeks whose revision pair is unchanged.
    """
    p = params()
    pairs = week_pairs(revs, weeks)
    f = Path(cache_file)
    cols = ["ticker", "week", "from_rev", "to_rev", "sentence"]
    read = lambda g: pd.read_csv(g, parse_dates=["week"], keep_default_na=False)
    if f.exists():
        out = read(f)
    elif seed_file is not None and Path(seed_file).exists():
        key = ["week", "from_rev", "to_rev"]
        out = read(seed_file).merge(pairs[key], on=key)[cols]
    else:
        out = pd.DataFrame(columns=cols)
    todo = pairs[~pairs["week"].isin(out["week"])]
    rows = []
    for i, w in enumerate(todo.itertuples(), 1):
        sents = added_sentences(compare(w.from_rev, w.to_rev, lang), p["min_words"])[: p["max_sentences_week"]]
        rows += [{"ticker": ticker, "week": w.week, "from_rev": w.from_rev, "to_rev": w.to_rev, "sentence": s}
                 for s in sents or [""]]
        if i % CHECKPOINT_WEEKS == 0 or i == len(todo):
            out = pd.concat([out, pd.DataFrame(rows, columns=cols)], ignore_index=True)
            rows = []
            f.parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(f, index=False)
    return out[out["week"].isin(pairs["week"])].reset_index(drop=True)


CACHE_TICKER = "wikipedia"   # ScoreCache keys on (post_id, ticker); a sentence's score doesn't depend on the stock


def score(sentences: list[str], cache_dir: Path | None = None) -> pd.DataFrame:
    """One row per sentence, in order: label, sentiment_pos/neg/neu and sentiment_net (pos - neg).

    Scored by the shared `FinbertScorer`; with `cache_dir`, scores are kept in its `ScoreCache` keyed by the
    sentence's hash, so reruns and repeated sentences are scored once.
    """
    texts = [prepare_text(None, s) for s in sentences]
    items = pd.DataFrame({"text": texts}).drop_duplicates()
    items = items.assign(post_id=items["text"].map(text_sha1), ticker=CACHE_TICKER)
    cache = ScoreCache(str(cache_dir)) if cache_dir is not None else None
    scored = score_items(items, FinbertScorer.from_config(), cache).set_index("text")
    out = scored.reindex(texts).reset_index(drop=True)
    out = out.rename(columns={"sentiment_label": "label"})[["label", "sentiment_pos", "sentiment_neg", "sentiment_neu"]]
    return out.assign(sentiment_net=out["sentiment_pos"] - out["sentiment_neg"])


def weekly_sentiment(scored: pd.DataFrame) -> pd.DataFrame:
    """Per ticker-week: the mean of each probability, sentiment_net = pos - neg, n_scored, and label counts.

    `n_pos` / `n_neg` count sentences labelled positive / negative (a week is "negative" when n_neg > n_pos).
    Weeks whose edits added no sentence have n_scored 0 and NaN probabilities.
    """
    s = scored[scored["sentence"].ne("")].assign(pos=lambda d: d["label"].eq("positive"),
                                                 neg=lambda d: d["label"].eq("negative"))
    g = s.groupby(["ticker", "week"])
    out = g[["sentiment_pos", "sentiment_neg", "sentiment_neu"]].mean()
    out["sentiment_net"] = out["sentiment_pos"] - out["sentiment_neg"]
    out = out.assign(n_scored=g.size(), n_pos=g["pos"].sum(), n_neg=g["neg"].sum())
    weeks = scored[["ticker", "week"]].drop_duplicates().set_index(["ticker", "week"])
    out = weeks.join(out).reset_index()
    return out.fillna({"n_scored": 0, "n_pos": 0, "n_neg": 0}).astype({"n_scored": int, "n_pos": int, "n_neg": int})


def stale(scored: pd.DataFrame) -> pd.Series:
    """True for sentences about old history: every year they name is >= STALE_YEARS before their week.

    Editors often re-add or rewrite history sections, so much "new" text is not news; sentences
    naming no year are not stale.
    """
    latest = scored["sentence"].str.findall(YEAR).apply(lambda ys: max(map(int, ys)) if ys else np.nan)
    return latest <= pd.to_datetime(scored["week"]).dt.year - STALE_YEARS


def sentiment_returns(weekly: pd.DataFrame, prices: pd.DataFrame, view_spikes: pd.DataFrame | None = None,
                      n_resamples: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Abnormal returns in weeks whose edits were mostly negative (positive) minus other scored weeks.

    Same week (`abn_ret`, the reaction) and the 1-4 weeks after (`abn_ret_next{k}`, a prediction),
    with week-cluster block bootstrap CIs (block = k). With `view_spikes` (ticker, week, spike), only
    view-spike weeks are compared: negative-edit spikes minus positive-edit spikes.
    """
    from src.wiki_prices import bootstrap_diff
    d = weekly[weekly["n_scored"] > 0].merge(prices, on=["ticker", "week"])
    d = d.assign(negative=d["n_neg"] > d["n_pos"], positive=d["n_pos"] > d["n_neg"])
    groups = {"negative edits vs rest": (d, "negative"), "positive edits vs rest": (d, "positive")}
    if view_spikes is not None:
        s = d.merge(view_spikes, on=["ticker", "week"])
        s = s[s["spike"] & (s["negative"] | s["positive"])]
        groups["view spikes: negative vs positive edits"] = (s, "negative")
    rows = []
    for name, (df, flag) in groups.items():
        for k, col in enumerate(["abn_ret", *[f"abn_ret_next{k}" for k in range(1, 5)]]):
            r = bootstrap_diff(df, col, flag=flag, n_resamples=n_resamples, seed=seed, block=max(k, 1))
            rows.append({"comparison": name, **r})
    return pd.DataFrame(rows)


def build(period: str = "research", tickers: list[str] | None = None, strategy: bool = False) -> pd.DataFrame:
    """Fetch, score and save weekly edit sentiment for the tracked stocks (or `tickers`) in one period.

    With `strategy`, it covers the whole strategy universe and writes `*_{period}_strategy.csv`, leaving the
    tracked-stock files (the Week 2 results) as they are.
    """
    from src.wiki_pipeline import (
        PROCESSED,
        article_starts,
        cache_stem,
        last_complete_sunday,
        period_dir,
        title_revisions,
        universe,
        untagged_dir,
        windows,
    )
    win = windows(last_complete_sunday())
    start, end = win[period]
    first_monday = start + pd.Timedelta(days=(7 - start.dayofweek) % 7)
    weeks = pd.date_range(first_monday, end - pd.Timedelta(days=6), freq="7D")   # full weeks only
    frames = []
    for tk, titles in universe("US", strategy=strategy).items():
        if tickers and tk not in tickers:
            continue
        revs = title_revisions(tk, titles, win)
        starts = article_starts(revs)
        for key, r in revs.groupby("key"):   # each article from its first week as an article
            lang, title = r["lang"].iloc[0], r["title"].iloc[0]
            name = f"{cache_stem(tk, titles, lang, title)}.csv"
            cache, seed = period_dir("diffs", period) / lang / name, untagged_dir("diffs", period) / lang / name
            frames.append(week_sentences(tk, r, weeks[weeks >= starts[key]], cache, lang, seed))
            print(tk, title, len(frames[-1]), "rows", flush=True)
    sents = pd.concat(frames, ignore_index=True)
    has = sents["sentence"].ne("")
    scores = score(sents.loc[has, "sentence"].tolist(), PROCESSED / "finbert_cache")
    scored = sents.join(scores.set_index(sents.index[has]))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tag = f"{period}_strategy" if strategy else period
    scored.to_csv(PROCESSED / f"edit_sentiment_sentences_{tag}.csv", index=False)
    weekly = weekly_sentiment(scored)
    weekly.to_csv(PROCESSED / f"edit_sentiment_weekly_{tag}.csv", index=False)
    return weekly


def analyse(period: str = "research") -> dict:
    """Label shares, stale share and `sentiment_returns` from the saved scores; writes results/wikipedia/."""
    from src.wiki_analysis import spike_flags
    from src.wiki_pipeline import PROCESSED, ROOT, shared_path
    from src.wiki_prices import research_only
    sc = pd.read_csv(PROCESSED / f"edit_sentiment_sentences_{period}.csv", parse_dates=["week"],
                     keep_default_na=False)
    sc = sc[sc["sentence"] != ""]
    weekly = pd.read_csv(PROCESSED / f"edit_sentiment_weekly_{period}.csv", parse_dates=["week"])
    prices = research_only(pd.read_csv(PROCESSED / "weekly_prices.csv", parse_dates=["week"]),
                           pd.Timestamp(config.holdout_start()))
    spikes = spike_flags(pd.read_csv(shared_path(period)), "wikipedia_views")[["week", "ticker", "spike"]]
    boot = config.load()["wikipedia"]["bootstrap"]
    res = sentiment_returns(weekly, prices, spikes, boot["n_resamples"], boot["seed"])
    scored = weekly[weekly["n_scored"] > 0].merge(prices, on=["ticker", "week"])
    is_stale = stale(sc)
    summary = {"ticker_weeks_with_edits": len(weekly), "ticker_weeks_scored": int((weekly["n_scored"] > 0).sum()),
               "sentences": len(sc), **{f"share_{k}": v for k, v in sc["label"].value_counts(normalize=True).items()},
               "share_stale": is_stale.mean(), "share_negative_stale": sc.loc[is_stale, "label"].eq("negative").mean(),
               "share_negative_fresh": sc.loc[~is_stale, "label"].eq("negative").mean(),
               "corr_net_same_week": scored["sentiment_net"].corr(scored["abn_ret"]),
               "corr_net_next_week": scored["sentiment_net"].corr(scored["abn_ret_next1"])}
    out = ROOT / "results" / "wikipedia"
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "edit_sentiment_returns.csv", index=False)
    pd.Series(summary).to_csv(out / "edit_sentiment_summary.csv", header=["value"])
    return {"summary": summary, "returns": res}


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["strategy"]:      # all strategy-universe stocks, for the Week 3 S4 strategy
        build("research", strategy=True)
        sys.exit()
    if sys.argv[1:] != ["analyse"]:
        build("research")
    r = analyse("research")
    print(pd.Series(r["summary"]).round(3).to_string())
    print(r["returns"].round(4).to_string(index=False))
