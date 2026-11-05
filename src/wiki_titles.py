"""Check that every Wikipedia title in config.yaml is the right company's article.

For each (stock, language, title) it asks Wikipedia whether the page exists, is the article itself
(not a redirect or a disambiguation page), and which Wikidata item it belongs to; then whether that
item lists the stock's ticker (P414 stock exchange, qualifier P249 ticker symbol). A title fails if it
is missing, a redirect or a disambiguation page. A missing ticker is only a warning: Wikidata often
leaves it off a subsidiary (Google) or a company that is also a product (Netflix).

    python -m src.wiki_titles            # every market; prints the table, exits 1 if a title fails
"""
import sys

import pandas as pd

from src import config
from src.wiki_attention import ACTION_API_URL, REQUEST_TIMEOUT_S, SESSION, user_agent
from src.wiki_pipeline import article_titles, universe

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
MAX_TITLES = 50   # titles (or Wikidata ids) per API request


def _get(url: str, params: dict) -> dict:
    r = SESSION.get(url, params={**params, "format": "json"}, headers=user_agent(), timeout=REQUEST_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def page_info(titles: list[str], lang: str) -> dict[str, dict]:
    """Title -> {exists, redirect_to, disambiguation, wikidata} from one language's Wikipedia."""
    out = {}
    for i in range(0, len(titles), MAX_TITLES):
        chunk = titles[i:i + MAX_TITLES]
        q = _get(ACTION_API_URL.format(lang=lang), {"action": "query", "titles": "|".join(chunk), "redirects": 1,
                                                    "prop": "pageprops", "formatversion": 2})["query"]
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        pages = {p["title"]: p for p in q["pages"]}
        for t in chunk:
            shown = norm.get(t, t)
            page = pages.get(redir.get(shown, shown), {})
            props = page.get("pageprops", {})
            out[t] = {"exists": bool(page) and not page.get("missing", False),
                      "redirect_to": redir.get(shown), "disambiguation": "disambiguation" in props,
                      "wikidata": props.get("wikibase_item")}
    return out


def wikidata_tickers(ids: list[str]) -> dict[str, set[str]]:
    """Wikidata id -> ticker symbols listed on its stock exchange claims."""
    out = {}
    for i in range(0, len(ids), MAX_TITLES):
        ents = _get(WIKIDATA_API_URL, {"action": "wbgetentities", "ids": "|".join(ids[i:i + MAX_TITLES]),
                                       "props": "claims"})["entities"]
        for qid, e in ents.items():
            out[qid] = {q["datavalue"]["value"] for c in e.get("claims", {}).get("P414", [])
                        for q in c.get("qualifiers", {}).get("P249", []) if "datavalue" in q}
    return out


def check(market: str) -> pd.DataFrame:
    """One row per configured title of a market's tracked and strategy stocks, with `ok` and `ticker_listed`."""
    rows = [{"market": market, "ticker": tk, "lang": lang, "title": t}
            for tk, titles in universe(market).items() for lang, t in article_titles(titles)]
    df = pd.DataFrame(rows, columns=["market", "ticker", "lang", "title"])
    if df.empty:
        return df
    info = {(lang, t): v for lang, g in df.groupby("lang") for t, v in page_info(g["title"].tolist(), lang).items()}
    df = df.join(pd.DataFrame([info[(r.lang, r.title)] for r in df.itertuples()], index=df.index))
    listed = wikidata_tickers(sorted(set(df["wikidata"].dropna())))
    # Yahoo writes BRK-B, Wikidata BRK.B; Indian and Hong Kong symbols carry a .NS / .HK suffix
    base = df["ticker"].str.replace("-", ".").str.split(r"\.(?:NS|BO|HK)$", regex=True).str[0]
    df["ticker_listed"] = [b in listed.get(q, set()) or tk in listed.get(q, set())
                           for b, tk, q in zip(base, df["ticker"], df["wikidata"])]
    df["ok"] = df["exists"] & df["redirect_to"].isna() & ~df["disambiguation"]
    return df


if __name__ == "__main__":
    res = pd.concat([df for m in config.markets() if len(df := check(m))], ignore_index=True)   # IN/HK may be empty
    print(res.to_string(index=False))
    bad, warn = res[~res["ok"]], res[res["ok"] & ~res["ticker_listed"]]
    print(f"\n{len(res)} titles: {len(bad)} fail, {len(warn)} without the ticker on Wikidata "
          f"({', '.join(warn['title']) or 'none'})")
    sys.exit(1 if len(bad) else 0)
