"""Static dashboard export: the page rewrite and the files the page will request."""
import json
import re

import pytest

from src.reddit import dashboard_export as de
from src.reddit import settings


def test_page_rewrite_reads_static_json_and_disables_pipeline_buttons():
    page = de.static_page((settings.DASHBOARD / "index.html").read_text(), "2026-11-09 02:00 UTC")
    assert 'fetch(f + ".json"' in page and "/charts/" not in page
    assert '$("runStrategies").disabled = true;' in page and "btn.disabled = true;" in page
    assert "data as of 2026-11-09 02:00 UTC" in page
    assert 'fetch(u, { cache: "no-store" })' not in page


def test_page_rewrite_fails_loudly_when_the_page_changes():
    with pytest.raises(ValueError, match="dashboard page changed"):
        de.static_page("<html><body>nothing to rewrite</body></html>", "now")


def test_export_writes_every_file_the_page_asks_for(tmp_path, monkeypatch):
    monkeypatch.setattr(de.ds, "status", lambda: {"range": ["a", "b"], "subreddits": []})
    monkeypatch.setattr(de.ds, "_csv", lambda p: {"rows": [], "updated": None})
    monkeypatch.setattr(de.ds, "weekly", lambda t: {"rows": [{"ticker": t}]})
    monkeypatch.setattr(de.ds, "strategy_run", lambda r: {"runs": ["run1"], "run_id": r or "run1", "series": {}})
    monkeypatch.setattr(settings, "CHARTS", tmp_path / "charts_src")
    (tmp_path / "charts_src").mkdir()
    (tmp_path / "charts_src" / "aapl_chatter_vs_price.png").write_bytes(b"png")
    out = tmp_path / "site"
    de.export(out)
    page = (out / "index.html").read_text()
    for name in re.findall(r'get\("/api/(\w+)"\)', page) + ["events", "spikes", "matches", "coverage"]:
        assert (out / "api" / f"{name}.json").exists(), name
    for t in settings.TICKERS:
        assert json.loads((out / "api/weekly" / f"{t}.json").read_text())["rows"][0]["ticker"] == t
    assert (out / "api/strategy_run/latest.json").exists() and (out / "api/strategy_run/run1.json").exists()
    assert (out / "charts/aapl_chatter_vs_price.png").read_bytes() == b"png"
