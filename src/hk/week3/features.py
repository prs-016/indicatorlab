"""Causal price and dated Wikipedia features for the five frozen hypotheses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from src import config
from src.hk.calendar import sessions
from src.hk.week3.public_data import CUTOFF, DATA, ROOT, get_json


@dataclass
class Bundle:
    """One market's bounded observations, past-only features and metadata."""

    market: str
    dates: pd.DatetimeIndex
    codes: list[str]
    prices: dict[str, pd.DataFrame]
    weekly: dict[str, pd.DataFrame]
    index: pd.DataFrame
    fx: pd.Series
    quality: dict


def monday(index) -> pd.DatetimeIndex:
    """Label all observations by their containing Monday, without a future shift."""
    return pd.DatetimeIndex(index).to_period("W-SUN").start_time


def weekly_last(frame):
    """Take each completed week's last observed market value."""
    return frame.groupby(monday(frame.index)).last()


def attention(ticker: str, intervals: pd.DataFrame) -> pd.DataFrame:
    """Fetch daily article-title views within evidenced title intervals, not all redirects."""
    destination = DATA / "attention" / (ticker + ".parquet")
    if destination.exists():
        return pd.read_parquet(destination)
    history = intervals[(intervals.symbol == ticker) & (intervals.lang == "en")]
    if history.empty:
        raise ValueError(f"No evidenced English title history for {ticker}")
    contributions = []
    for row in history.itertuples(index=False):
        begin = max(pd.Timestamp("2015-07-01", tz="UTC"), pd.Timestamp(row.valid_from))
        complete_week_end = (
            CUTOFF.tz_localize(None).to_period("W-SUN").start_time.tz_localize("UTC")
        )
        finish = min(
            complete_week_end,
            pd.Timestamp(row.valid_to) if pd.notna(row.valid_to) else complete_week_end,
        )
        if finish <= begin:
            continue
        # Include both observed titles on a move day, and disclose that day's sum.
        end_date = (finish - pd.Timedelta(seconds=1)).floor("D")
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/"
            + quote(row.title, safe="")
            + "/daily/"
            + begin.strftime("%Y%m%d00")
            + "/"
            + end_date.strftime("%Y%m%d00")
        )
        response = get_json(url)
        values = pd.Series(
            {
                pd.Timestamp(item["timestamp"][:8]): item["views"]
                for item in response["items"]
            },
            dtype=float,
        )
        values = values.loc[
            begin.tz_localize(None).floor("D") : end_date.tz_localize(None)
        ]
        contributions.append(values)
    if not contributions:
        raise ValueError(f"No pageview history before cutoff: {ticker}")
    daily = pd.concat(contributions, axis=1).sum(axis=1, min_count=1).sort_index()
    if (daily.index >= CUTOFF.tz_localize(None)).any():
        raise ValueError("Future pageviews")
    grouped = daily.groupby(monday(daily.index))
    views = grouped.sum(min_count=7).where(grouped.count() == 7)
    article = json.loads((DATA / "wikipedia" / (ticker + ".json")).read_text())
    edits = pd.Series(
        {pd.Timestamp(row["week"]): row["edits"] for row in article["weeks"]},
        dtype=float,
    )
    weeks = pd.date_range("2015-07-06", "2025-09-22", freq="W-MON")
    # A completely enumerated revision history proves a zero-edit week. Missing
    # text and missing pageview days are still missing observations.
    creation = pd.Timestamp(history.valid_from.min()).tz_localize(None)
    edits = edits.reindex(weeks, fill_value=0.0).where(weeks >= creation.normalize())
    result = pd.DataFrame({"views": views, "edits": edits}).reindex(weeks)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(destination)
    return result


def build_bundle(market: str, specification: dict) -> Bundle:
    """Build only expanding/rolling past-based features on actual exchange sessions."""
    settings = specification["markets"][market]
    codes = settings["symbols"]
    cal = xcals.get_calendar(
        "XHKG" if market == "HK" else "XNYS", start="2015-01-01", end="2025-09-30"
    )
    dates = (
        sessions("2015-01-01", "2025-09-30")
        if market == "HK"
        else pd.DatetimeIndex(cal.sessions).tz_localize(None)
    )
    fields = {key: {} for key in ("open", "close", "volume", "dividend")}
    quality = {
        "market": market,
        "rows_outside_calendar": {},
        "missing_on_session": {},
        "historical_lot_basis": (
            "current snapshot assumption" if market == "HK" else "fractional US shares"
        ),
    }
    for ticker in codes:
        frame = pd.read_parquet(DATA / "prices" / (ticker + ".parquet"))
        if frame.index.max() >= CUTOFF.tz_localize(None):
            raise ValueError("Holdout price loaded")
        quality["rows_outside_calendar"][ticker] = int((~frame.index.isin(dates)).sum())
        selected = frame.reindex(dates)
        listed = dates >= frame.index.min()
        quality["missing_on_session"][ticker] = int(
            (selected.close.isna() & listed).sum()
        )
        for key, column_values in fields.items():
            values = selected[key]
            column_values[ticker] = (
                values.fillna(0) if key in {"dividend", "volume"} else values
            )
    prices = {key: pd.DataFrame(value, index=dates) for key, value in fields.items()}
    close, volume = prices["close"], prices["volume"]
    daily = (close + prices["dividend"]) / close.shift(1) - 1
    rv20, rv63 = (
        daily.rolling(20, min_periods=20).std(),
        daily.rolling(63, min_periods=63).std(),
    )
    index_ticker = settings["benchmark"]
    index = pd.read_parquet(
        DATA / "prices" / (index_ticker.replace("^", "INDEX_") + ".parquet")
    ).reindex(dates)
    index_returns = (index.close + index.dividend.fillna(0)) / index.close.shift(1) - 1
    if index.close.isna().any():
        raise ValueError("Benchmark is missing an actual exchange session")
    index_vol = index_returns.rolling(63, min_periods=63).std() * np.sqrt(252)
    downside = index_returns.clip(upper=0).pow(2).rolling(
        20, min_periods=20
    ).mean().pow(0.5) * np.sqrt(252)
    beta = (
        daily.rolling(126, min_periods=126)
        .cov(index_returns)
        .div(index_returns.rolling(126, min_periods=126).var(), axis=0)
    )
    residual = daily.sub(beta.mul(index_returns, axis=0))
    residual_score = residual.rolling(5, min_periods=5).sum() / (
        residual.rolling(63, min_periods=63).std() * np.sqrt(5)
    )
    week_return = (1 + daily).groupby(monday(dates)).prod(min_count=1) - 1
    turn = (close * volume).groupby(monday(dates)).sum(min_count=1)
    baseline_weeks = int(config.spike_rule()["baseline_weeks"])
    index_week = pd.DataFrame(
        {
            "index_vol": weekly_last(index_vol),
            "index_vol_q90": weekly_last(
                index_vol.expanding(126).quantile(0.9).shift(1)
            ),
            "index_downside": weekly_last(downside),
            "index_downside_q75": weekly_last(
                downside.expanding(126).quantile(0.75).shift(1)
            ),
        }
    )
    history = pd.concat(
        [
            pd.read_csv(ROOT / "config/hk_wiki_title_intervals.csv"),
            pd.read_csv(ROOT / "config/us_wiki_title_intervals.csv"),
        ],
        ignore_index=True,
    )
    attention_frames = {ticker: attention(ticker, history) for ticker in codes}
    views = pd.DataFrame(
        {ticker: value.views for ticker, value in attention_frames.items()}
    )
    edits = pd.DataFrame(
        {ticker: value.edits for ticker, value in attention_frames.items()}
    )
    view_base = (
        views.shift(1).rolling(baseline_weeks, min_periods=baseline_weeks).median()
    )
    edit_base = (
        edits.shift(1).rolling(baseline_weeks, min_periods=baseline_weeks).median()
    )
    abnormal = np.log((views + 1) / (view_base + 1))
    market_attention = abnormal.mean(axis=1)
    previous = market_attention.shift(1)
    attention_z = (
        market_attention - previous.rolling(52, min_periods=26).mean()
    ) / previous.rolling(52, min_periods=26).std().replace(0, np.nan)
    sentiment = pd.read_parquet(DATA / "wiki_sentiment.parquet")
    sentiment["week"] = pd.to_datetime(sentiment.week)
    sentiment = sentiment.pivot(
        index="week", columns="ticker", values="sentiment"
    ).reindex(index=views.index, columns=codes)
    observed_sentiment = sentiment.rolling(4, min_periods=1).mean()
    weekly = {
        "return": week_return,
        "rv20": weekly_last(rv20),
        "rv63": weekly_last(rv63),
        "shock": week_return / (weekly_last(rv20) * np.sqrt(5)),
        "turnover": weekly_last((close * volume).rolling(63).median()),
        "volume_ratio": (turn + 1)
        / (
            turn.shift(1).rolling(baseline_weeks, min_periods=baseline_weeks).median()
            + 1
        ),
        "residual": weekly_last(residual_score),
        "compression": weekly_last(rv20 / rv63.replace(0, np.nan)),
        "view_ratio": (views + 1) / (view_base + 1),
        "edit_ratio": (edits + 1) / (edit_base + 1),
        "views": views,
        "sentiment": observed_sentiment,
    }
    weekly = {
        key: value.reindex(index=index_week.index, columns=codes)
        for key, value in weekly.items()
    }
    for key in index_week:
        weekly[key] = pd.DataFrame(
            np.repeat(index_week[key].to_numpy()[:, None], len(codes), axis=1),
            index=index_week.index,
            columns=codes,
        )
    weekly["attention_z"] = pd.DataFrame(
        np.repeat(
            attention_z.reindex(index_week.index).to_numpy()[:, None],
            len(codes),
            axis=1,
        ),
        index=index_week.index,
        columns=codes,
    )
    fx = pd.Series(1.0, index=dates)
    if market == "HK":
        raw_fx = pd.read_parquet(DATA / "prices/HKD=X.parquet").close.dropna()
        # The previous calendar day's FX close is already known at HK valuation.
        shifted = raw_fx.copy()
        shifted.index += pd.Timedelta(days=1)
        fx = (
            shifted.reindex(dates.union(shifted.index))
            .sort_index()
            .ffill()
            .reindex(dates)
        )
    return Bundle(market, dates, codes, prices, weekly, index, fx, quality)


def strategy_week(
    bundle: Bundle,
    strategy: dict,
    variant: dict,
    week: pd.Timestamp,
    drop: str | None = None,
):
    """Compute entry mask/rank and regime without looking beyond the completed week."""
    f = {key: frame.loc[week] for key, frame in bundle.weekly.items()}
    identifier = strategy["id"]
    scale = 1.0
    conditions = {}
    if identifier == "liquidity_repair":
        conditions = {
            "negative_volatility_scaled_return": f["shock"] < -variant["shock"],
            "turnover_ratio": f["volume_ratio"] >= variant["volume"],
            "wiki_views_ratio": f["view_ratio"] >= variant["views"],
            "wiki_added_text_sentiment": f["sentiment"] >= variant["sentiment"],
        }
        scale = 0.5 if f["index_vol"].iloc[0] > f["index_vol_q90"].iloc[0] else 1.0
        if drop == "index_volatility_regime":
            scale = 1.0
        rank = -f["shock"]
        if drop == "negative_volatility_scaled_return":
            rank = pd.Series(0.0, index=bundle.codes)
    elif identifier == "defensive_attention_gate":
        conditions = {
            "stock_volatility_rank": f["rv63"] <= f["rv63"].quantile(0.5),
            "turnover_rank": f["turnover"]
            >= f["turnover"].quantile(variant["liquidity_quantile"]),
            "wiki_added_text_sentiment": f["sentiment"] >= variant["sentiment"],
        }
        vol = f["index_vol"].iloc[0]
        scale = min(1.0, 0.10 / vol) if vol > 0 else 0.0
        if drop == "index_volatility_target":
            scale = 1.0
        if drop != "market_attention_risk_gate" and f["attention_z"].iloc[0] > 1.5:
            scale *= 0.5
        rank = (
            -f["rv63"]
            if drop != "stock_volatility_rank"
            else pd.Series(0.0, index=bundle.codes)
        )
    elif identifier == "residual_repair":
        conditions = {
            "residual_return_dislocation": f["residual"] < -variant["shock"],
            "volume_ratio": f["volume_ratio"] >= variant["volume"],
            "wiki_edit_ratio": f["edit_ratio"] >= variant["edits"],
            "wiki_added_text_sentiment": f["sentiment"] >= variant["sentiment"],
        }
        scale = (
            0.5
            if f["index_downside"].iloc[0] > f["index_downside_q75"].iloc[0]
            else 1.0
        )
        if drop == "index_downside_regime":
            scale = 1.0
        rank = -f["residual"]
        if drop == "residual_return_dislocation":
            rank = pd.Series(0.0, index=bundle.codes)
    elif identifier == "information_compression":
        conditions = {
            "volatility_compression": f["compression"] <= variant["compression"],
            "volume_ceiling": f["volume_ratio"] <= variant["volume_max"],
            "wiki_views_ratio": f["view_ratio"] >= variant["views"],
            "wiki_added_text_sentiment": f["sentiment"] >= variant["sentiment"],
        }
        scale = (
            0.5
            if f["index_downside"].iloc[0] > f["index_downside_q75"].iloc[0]
            else 1.0
        )
        if drop == "index_downside_regime":
            scale = 1.0
        rank = (
            -f["compression"]
            if drop != "volatility_compression"
            else pd.Series(0.0, index=bundle.codes)
        )
    else:
        prior_week = week - pd.Timedelta(days=7)
        old_ratio = bundle.weekly["view_ratio"].reindex([prior_week]).iloc[0]
        old_views = bundle.weekly["views"].reindex([prior_week]).iloc[0]
        conditions = {
            "prior_attention_spike": old_ratio >= variant["peak"],
            "attention_decay": f["views"] < old_views * variant["decay"],
            "negative_stock_return": f["return"] < 0,
            "volume_floor": f["volume_ratio"] >= variant["volume"],
            "wiki_added_text_sentiment": f["sentiment"] >= variant["sentiment"],
        }
        scale = 0.5 if f["index_vol"].iloc[0] > f["index_vol_q90"].iloc[0] else 1.0
        if drop == "index_volatility_regime":
            scale = 1.0
        rank = -f["shock"]
        if drop == "negative_stock_return":
            rank = pd.Series(0.0, index=bundle.codes)
    mask = pd.Series(True, index=bundle.codes)
    for name, condition in conditions.items():
        if name != drop:
            mask &= condition.fillna(False)
    # Feature absence is never made positive by an ablation. Sizing still needs
    # observed volatility and no entry is allowed before a complete lookback.
    mask &= f["rv63"].notna() & f["rv63"].gt(0)
    return mask, rank, scale


def make_plans(
    bundle: Bundle, strategy: dict, variant: dict, split: tuple[str, str], drop=None
):
    """Generate causal weekly entries and next-open exits, preserving an IC score panel."""
    start, end = (pd.Timestamp(value) for value in split)
    first, last = (
        bundle.dates.searchsorted(start),
        bundle.dates.searchsorted(end, side="right") - 1,
    )
    plans, scores = [], {}
    close, opens, dividend, volume = (
        bundle.prices[key] for key in ("close", "open", "dividend", "volume")
    )
    for week in bundle.weekly["rv63"].index:
        entry_day = week + pd.Timedelta(days=7)
        entry = int(bundle.dates.searchsorted(entry_day))
        next_week = int(bundle.dates.searchsorted(entry_day + pd.Timedelta(days=7)))
        exit_ = min(entry + 5, next_week)
        if entry < first or entry >= last or exit_ > last or exit_ <= entry:
            continue
        mask, rank, scale = strategy_week(bundle, strategy, variant, week, drop)
        score = rank.where(mask, 0.0).where(bundle.weekly["rv63"].loc[week].notna())
        scores[entry] = score.to_dict()
        selected = rank.where(mask).dropna().sort_values(ascending=False).head(10)
        if selected.empty or scale <= 0:
            continue
        inverse = 1 / bundle.weekly["rv63"].loc[week, selected.index]
        if drop == "stock_volatility_rank":
            inverse = pd.Series(1.0, index=selected.index)
        weights = (inverse / inverse.sum()).clip(upper=0.1) * scale
        for code in selected.index:
            price = opens.iloc[entry][code]
            if not np.isfinite(price) or price <= 0 or volume.iloc[entry][code] <= 0:
                continue
            stop_exit, cash_div = exit_, 0.0
            for day in range(entry, exit_):
                if day > entry:
                    cash_div += dividend.iloc[day][code]
                mark = close.iloc[day][code]
                if (
                    np.isfinite(mark)
                    and (mark + cash_div) / (price * 1.001) - 1 <= -strategy["stop"]
                ):
                    stop_exit = min(day + 1, exit_)
                    break
            while stop_exit <= last and (
                not np.isfinite(opens.iloc[stop_exit][code])
                or opens.iloc[stop_exit][code] <= 0
                or volume.iloc[stop_exit][code] <= 0
            ):
                stop_exit += 1
            if stop_exit > last:
                continue
            plans.append(
                {
                    "symbol": code,
                    "entry": entry,
                    "exit": stop_exit,
                    "weight": float(weights[code]),
                    "reason": "close_stop" if stop_exit < exit_ else "weekly_max_hold",
                }
            )
    return plans, scores, (int(first), int(last))
