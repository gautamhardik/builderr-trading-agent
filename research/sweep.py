"""Evaluate several agent specs in parallel over the same windows (compact output).

    python research/sweep.py --last 2021-12-31 research/candidates/trend_breadth.py "research/candidates/trend_breadth.py:TOP_K=4"
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data  # noqa: E402
import engine  # noqa: E402
import windows  # noqa: E402

_CTX = {}


def _init(first, last, n):
    market = engine.Market(data.load())
    starts = windows.window_starts(market, first, last, n, 5)
    _CTX.update(market=market, starts=starts, n=n, board=windows.board_now(),
                arnav=windows.arnav_moves(market, starts, n), qqq=windows.qqq_moves(market, starts, n))


def _one(spec):
    c = _CTX
    return windows.evaluate(spec, c["market"], c["starts"], c["n"], c["arnav"], c["qqq"], c["board"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--sessions", type=int, default=15)
    ap.add_argument("--first", default="2013-06-01")
    ap.add_argument("--last", default="2026-12-31")
    args = ap.parse_args()
    _init(args.first, args.last, args.sessions)  # warm the Arnav cache once before forking
    with ProcessPoolExecutor(max_workers=min(8, len(args.specs)), initializer=_init,
                             initargs=(args.first, args.last, args.sessions)) as pool:
        results = list(pool.map(_one, args.specs))
    print(f"{len(_CTX['starts'])} windows  {args.first}..{args.last}")
    for r in results:
        print(f"  {r['agent'][:46]:46s} mean {r['mean']*100:+5.2f}%  sd {r['sd']*100:4.1f}%  "
              f"beatArnav {r['p_beat_arnav']*100:5.1f}%  points {r['p_points']*100:5.1f}%  prize {r['p_prize']*100:4.1f}%  "
              f"worst {r['worst']*100:+6.1f}%  mdd {r['worst_mdd']*100:4.1f}%  gross {r['peak_gross']:.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
