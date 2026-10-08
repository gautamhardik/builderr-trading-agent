"""Fetch and cache daily bars for the live Round 2 universe.

Mirrors live_runner.fetch_bars(): yfinance daily bars, auto_adjust=True, and the same
ticker list the live board actually scores (live_runner.UNIVERSE, 42 names).

    python research/data.py            # refresh the cache
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data_cache" / "bars_daily.json.gz"
START = "2012-01-01"


def live_universe() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from live_runner import UNIVERSE  # noqa: PLC0415 — the board's real scored list
    return list(UNIVERSE)


def fetch(start: str = START) -> dict[str, list[list]]:
    import yfinance as yf  # noqa: PLC0415

    tickers = live_universe()
    raw = yf.download(tickers, start=start, interval="1d", auto_adjust=True,
                      progress=False, threads=True, group_by="ticker")
    bars: dict[str, list[list]] = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Open", "High", "Low", "Close"])
        except KeyError:
            continue
        rows = [
            [ts.strftime("%Y-%m-%d"), float(o), float(h), float(l), float(c), int(v) if v == v else 0]
            for ts, o, h, l, c, v in zip(df.index, df["Open"], df["High"], df["Low"], df["Close"], df["Volume"])
        ]
        if rows:
            bars[t] = rows
    return bars


def load() -> dict[str, list[list]]:
    """Compact bars {ticker: [[ts, o, h, l, c, v], ...]} from the cache (fetch if missing)."""
    if not CACHE.exists():
        save(fetch())
    return json.loads(gzip.open(CACHE, "rb").read())


def save(bars: dict[str, list[list]]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wb") as f:
        f.write(json.dumps(bars).encode())


if __name__ == "__main__":
    b = fetch()
    save(b)
    last = max(rows[-1][0] for rows in b.values())
    print(f"cached {len(b)} tickers through {last} -> {CACHE}")
    for t, rows in sorted(b.items()):
        print(f"  {t:5s} {rows[0][0]} .. {rows[-1][0]}  ({len(rows)} bars)")
