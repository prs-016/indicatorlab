import pandas as pd

from src import wiki_titles


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _fake_get(url, params=None, **kw):
    if "wikidata" in url:
        return _Resp({"entities": {
            "Q1": {"claims": {"P414": [{"qualifiers": {"P249": [{"datavalue": {"value": "AAA"}}]}}]}},
            "Q2": {"claims": {}}}})
    return _Resp({"query": {
        "normalized": [{"from": "A_Inc.", "to": "A Inc."}, {"from": "Old_B", "to": "Old B"}],
        "redirects": [{"from": "Old B", "to": "B"}],
        "pages": [{"title": "A Inc.", "pageprops": {"wikibase_item": "Q1"}},
                  {"title": "B", "pageprops": {"wikibase_item": "Q2"}},
                  {"title": "C", "pageprops": {"disambiguation": "", "wikibase_item": "Q3"}},
                  {"title": "Nope", "missing": True}]}})


def test_check_flags_redirects_disambiguation_missing_pages_and_unlisted_tickers(monkeypatch):
    monkeypatch.setenv("WIKIMEDIA_CONTACT", "test@example.org")
    monkeypatch.setattr(wiki_titles.SESSION, "get", _fake_get)
    monkeypatch.setattr(wiki_titles, "universe", lambda market: {
        "AAA": {"en": "A_Inc."}, "BBB": {"en": ["Old_B", "C"]}, "DDD": {"en": "Nope"}})
    out = wiki_titles.check("US").set_index("title")
    assert out["ok"].to_dict() == {"A_Inc.": True, "Old_B": False, "C": False, "Nope": False}
    assert out.loc["Old_B", "redirect_to"] == "B" and out.loc["C", "disambiguation"]
    assert out.loc["A_Inc.", "ticker_listed"] and not out.loc["Old_B", "ticker_listed"]


def test_check_of_an_empty_market_is_empty(monkeypatch):
    monkeypatch.setattr(wiki_titles, "universe", lambda market: {})
    assert wiki_titles.check("IN").empty and isinstance(wiki_titles.check("IN"), pd.DataFrame)
