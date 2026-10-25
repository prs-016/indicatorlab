
from src.reddit.match_tickers import match_post


def tickers(title, body=""):
    return {r["ticker"]: r for r in match_post(title, body)}


def test_cashtag_ticker_and_name_methods():
    r = tickers("$aapl to the moon", "")
    assert r["AAPL"]["match_method"] == "cashtag"
    assert tickers("Bought MSFT today")["MSFT"]["match_method"] == "ticker"
    assert tickers("Nvidia earnings next week")["NVDA"]["match_method"] == "company_name"


def test_title_and_body_are_both_searched():
    assert tickers("Thoughts?", "I hold TSLA")["TSLA"]["found_in"] == "body"
    assert tickers("TSLA", "Tesla deliveries")["TSLA"]["found_in"] == "both"


def test_one_row_per_ticker_strongest_method():
    rows = match_post("$NVDA NVDA Nvidia", "NVDA again")
    nv = [r for r in rows if r["ticker"] == "NVDA"]
    assert len(nv) == 1 and nv[0]["match_method"] == "cashtag"
    assert nv[0]["all_methods"] == "cashtag;ticker;company_name"


def test_multiple_companies_in_one_post():
    assert set(tickers("AAPL vs MSFT vs GOOG")) == {"AAPL", "MSFT", "GOOGL"}


def test_word_boundaries():
    assert "AMD" not in tickers("AMD64 build", "")
    assert "AMD" not in tickers("I am damned")
    assert "JPM" not in tickers("JPMX fund")
    assert "AMD" not in tickers("amd is lowercase so ignored")


def test_meta_ambiguity():
    assert "META" not in tickers("the meta has shifted in this game")
    assert "META" not in tickers("Meta thread: rules of the sub")
    assert "META" not in tickers("A Meta-analysis of returns")
    assert "META" not in tickers("Meta discussion about moderation")  # no company context
    assert tickers("Meta earnings beat")["META"]["match_method"] == "company_name"
    assert "META" in tickers("Meta's capex is huge")
    assert "META" in tickers("Meta is spending a lot", "Zuckerberg said so")
    assert tickers("$META calls")["META"]["match_method"] == "cashtag"
    assert "META" in tickers("Facebook ads revenue")


def test_common_word_names():
    assert "AAPL" not in tickers("an apple a day")
    assert "AAPL" not in tickers("Moving to the Big Apple")
    assert "AAPL" not in tickers("Apple Hospitality REIT dividend")
    assert "AAPL" in tickers("Apple Vision Pro launch")
    assert "AMZN" not in tickers("Amazon rainforest fires")
    assert "AMZN" in tickers("Amazon AWS growth")
    assert "GOOGL" not in tickers("learn the alphabet")
    assert "GOOGL" not in tickers("just Google it")
    assert "TSLA" not in tickers("Nikola Tesla invented AC")
    assert "JPM" not in tickers("chase the trend")
    assert "JPM" in tickers("J.P. Morgan downgrade")
    assert "JPM" in tickers("JPMorgan Chase earnings")


def test_urls_and_removed_bodies_ignored():
    assert "AMZN" not in tickers("Check this", "https://www.amazon.com/dp/123")
    assert "GOOGL" not in tickers("link", "see docs.google.com/abc")
    assert tickers("x", "[removed]") == {}
