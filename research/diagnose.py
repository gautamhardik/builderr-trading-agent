"""Where does an agent lose to Arnav? Splits dev windows by what Arnav and QQQ did.

    python research/diagnose.py research/candidates/trend_breadth.py --last 2021-12-31
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data  # noqa: E402
import engine  # noqa: E402
import windows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--sessions", type=int, default=15)
    ap.add_argument("--first", default="2013-06-01")
    ap.add_argument("--last", default="2026-12-31")
    args = ap.parse_args()

    market = engine.Market(data.load())
    board = windows.board_now()
    starts = windows.window_starts(market, args.first, args.last, args.sessions, 5)
    arnav = windows.arnav_moves(market, starts, args.sessions)
    qqq = windows.qqq_moves(market, starts, args.sessions)
    factory = windows.load_spec(args.agent)
    rows = []
    for i in starts:
        r = engine.run(factory(), market, market.dates[i], market.dates[i + args.sessions - 1])
        need = (1 + board["arnav"]) * (1 + arnav[i]) - 1
        rows.append((i, r["ret"], arnav[i], qqq[i], r["ret"] > need))

    def show(label, sel):
        if not sel:
            return
        print(f"  {label:34s} n={len(sel):4d}  win {sum(s[4] for s in sel) / len(sel) * 100:5.1f}%  "
              f"ours {statistics.fmean(s[1] for s in sel) * 100:+5.1f}%  arnav {statistics.fmean(s[2] for s in sel) * 100:+5.1f}%  "
              f"qqq {statistics.fmean(s[3] for s in sel) * 100:+5.1f}%")

    print(f"{args.agent}: {len(rows)} windows")
    show("all", rows)
    show("Arnav up > 2%", [r for r in rows if r[2] > 0.02])
    show("Arnav flat (-2%..2%)", [r for r in rows if -0.02 <= r[2] <= 0.02])
    show("Arnav down < -2%", [r for r in rows if r[2] < -0.02])
    show("QQQ up > 3%", [r for r in rows if r[3] > 0.03])
    show("QQQ flat", [r for r in rows if -0.03 <= r[3] <= 0.03])
    show("QQQ down < -3%", [r for r in rows if r[3] < -0.03])
    losses = sorted((r for r in rows if not r[4]), key=lambda r: r[1] - r[2])[:8]
    print("  worst relative losses (start, ours, arnav, qqq):")
    for i, ours, arn, q, _ in losses:
        print(f"    {market.dates[i]}  {ours * 100:+6.1f}%  {arn * 100:+6.1f}%  {q * 100:+6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
