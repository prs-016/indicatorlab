import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

tickers = [
    "0700.HK", "0005.HK", "1299.HK",
    "0941.HK", "0388.HK", "^HSI"
]

folder = Path(__file__).resolve().parent / "data"
folder.mkdir(exist_ok=True)
history = {}

parser = argparse.ArgumentParser(
    description="Download (optionally) and audit the Hong Kong week-1 data."
)
parser.add_argument(
    "--refresh",
    action="store_true",
    help="Download fresh Yahoo Finance files. Without this flag, audit existing CSVs.",
)
args = parser.parse_args()

for symbol in tickers:
    path = folder / f"{symbol}.csv"

    if args.refresh or not path.exists():
        print(f"Downloading {symbol}...")

        try:
            df = yf.Ticker(symbol).history(
                start="2021-01-01",
                end="2025-01-01",
                auto_adjust=False,
            )
        except Exception as e:
            print(f"Download failed: {e}")
            continue

        if df.empty:
            print(f"No data found for {symbol}")
            continue

        df.index = pd.to_datetime(df.index.date)
        df.index.name = "Date"
        df.to_csv(path)
        print(f"Saved {len(df)} trading days")
    else:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        print(f"Loaded {symbol}: {len(df)} existing rows")

    if df.empty:
        print(f"No data found for {symbol}")
        continue

    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    history[symbol] = df

if "^HSI" not in history:
    print("WARNING: Benchmark download failed.")

reference = set(history["^HSI"].index) if "^HSI" in history else set()
results = []

for symbol, df in history.items():
    adjusted = df.get("Adj Close", df["Close"])
    returns = adjusted.pct_change(fill_method=None)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing_required = df[required].isna().any(axis=1)
    impossible_ohlc = (
        (df["High"] < df[["Open", "Low", "Close"]].max(axis=1))
        | (df["Low"] > df[["Open", "High", "Close"]].min(axis=1))
    )
    zero_volume = df["Volume"].eq(0)
    flat_ohlc = df[["Open", "High", "Low", "Close"]].nunique(axis=1).eq(1)

    results.append({
        "Ticker": symbol,
        "First date": str(df.index.min().date()),
        "Last date": str(df.index.max().date()),
        "Trading days": len(df),
        "Missing vs HSI": len(reference - set(df.index)),
        "Duplicate dates": int(df.index.duplicated().sum()),
        "Rows missing OHLCV": int(missing_required.sum()),
        "Invalid close": int(
            (df["Close"].isna() | (df["Close"] <= 0)).sum()
        ),
        "Impossible OHLC": int(impossible_ohlc.sum()),
        "Negative volume": int((df["Volume"] < 0).sum()),
        "Zero volume": int(zero_volume.sum()),
        "Flat OHLC + zero volume": int((flat_ohlc & zero_volume).sum()),
        "Daily moves over 25%": int(
            (returns.abs() > 0.25).sum()
        )
    })

summary = pd.DataFrame(results)
summary.to_csv(folder / "data_checks.csv", index=False)

print("\nDATA QUALITY SUMMARY")
print(summary.to_string(index=False))
