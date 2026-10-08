"""Prove the research harness matches the live board before trusting any result from it.

  1. Parity: research.engine.run == live_runner.run_bot on identical bars.
  2. Reality: replaying Arnav's agent over Round 2 reproduces his published live curve.

    python research/validate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

import data  # noqa: E402
import engine  # noqa: E402
import live_runner  # noqa: E402

ARNAV = ROOT / "private_agents" / "arnav_agent.py"


def parity(compact):
    lo, hi, entry = "2024-01-01", "2025-04-30", "2025-02-03"
    window = {t: [r for r in rows if lo <= r[0] <= hi] for t, rows in compact.items()}
    window = {t: rows for t, rows in window.items() if rows}
    market = engine.Market(window)
    ours = engine.run(engine.load_agent(ARNAV), market, entry, hi, history=10**9)
    theirs = live_runner.run_bot(engine.load_agent(ARNAV), market.bars, entry)
    worst = max(abs(a - b) for a, b in zip(ours["curve"], theirs["curve"]))
    same_len = len(ours["curve"]) == len(theirs["curve"])
    print(f"[parity] {entry}..{hi}: {len(ours['curve'])} sessions, trades {ours['trades']} vs {theirs['trades']}, "
          f"max curve diff ${worst:.4f}, ret {ours['ret']*100:+.2f}% vs {theirs['ret']*100:+.2f}%")
    return same_len and worst < 0.02 and ours["trades"] == theirs["trades"]


def reality(compact):
    published = json.loads((ROOT / "private_results.json").read_text())["arnav"]
    asof, need = published["as_of"], live_runner.EVAL_DAYS + live_runner.WARMUP_DAYS + 30
    # The board fetches a fresh window each run and keeps the last `need` bars per ticker.
    window = {t: [r for r in rows if r[0] <= asof][-need:] for t, rows in compact.items()}
    market = engine.Market(window)
    res = engine.run(engine.load_agent(ARNAV), market, published["since"], asof)
    pub = published["curve"][-len(res["curve"]):]
    diffs = [abs(a / b - 1) for a, b in zip(res["curve"], pub)]
    print(f"[reality] Arnav {published['since']}..{asof}: replay {res['ret']*100:+.2f}% "
          f"({res['trades']} trades) vs published {published['ret']*100:+.2f}% ({published['trades']} trades)")
    print(f"          worst daily equity gap {max(diffs)*100:.2f}%, final-day gap {diffs[-1]*100:.2f}% "
          f"(board's last bar was intraday at 19:30Z, so the last day can differ)")
    return max(diffs[:-1]) < 0.01


if __name__ == "__main__":
    bars = data.load()
    ok = parity(bars) & reality(bars)
    print("HARNESS OK" if ok else "HARNESS MISMATCH — investigate before trusting results")
    sys.exit(0 if ok else 1)
