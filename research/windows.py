"""Short-window forward evaluation — the question that matters for a late Round 2 entry.

A bot admitted now is scored only from its first session to Oct 30 (~15 sessions), but it
is ranked against entrants carrying ~2-3 months of head start. So for each agent we replay
every historical N-session window (fresh state at entry, exactly like a new live bot) and ask:

  * beat Arnav?  ours > (1 + arnav_now) * (1 + arnav's move over the same window) - 1
                 (Arnav is replayed warm — started 66 sessions earlier — like the live board)
  * points / prize? rank among entrants that beat Arnav is <= 10 / <= 3. Every current
                 entrant is simulated from its own live curve: final = (1 + now) *
                 (1 + beta * QQQ window move + residual noise), with beta and daily
                 residual vol fitted on its scored days (Monte Carlo over the noise).

    python research/windows.py agent.py private_agents/arnav_agent.py research/probes/max_beta_tqqq.py
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))

import data  # noqa: E402
import engine  # noqa: E402

ARNAV = ROOT / "private_agents" / "arnav_agent.py"
ARNAV_WARM = 66  # sessions Arnav has already traded in Round 2 by Oct 7
DRAWS = 40       # Monte Carlo draws of the field per window


def board_now() -> dict:
    lb = json.loads((ROOT / "leaderboard.json").read_text())
    entrants = sorted((b["ret"] for b in lb["bots"] if "entrant" in b["label"] and b["as_of"] == lb["as_of_market_date"]),
                      reverse=True)
    return {"arnav": lb["benchmark"]["ret"], "rank1": entrants[0], "rank3": entrants[2], "rank10": entrants[9],
            "as_of": lb["as_of_market_date"], "field": fit_field(lb)}


def fit_field(lb) -> list[tuple[float, float, float]]:
    """(return now, beta to the board's market curve, daily residual vol) per current entrant."""
    curves = json.loads((ROOT / "private_results.json").read_text())
    market = json.loads((ROOT / "history.json").read_text())["market"]["curve"]
    field = []
    for b in lb["bots"]:
        rec = curves.get(b["name"])
        if "entrant" not in b["label"] or b["as_of"] != lb["as_of_market_date"] or not rec or rec["days"] < 5:
            continue
        c = rec["curve"][-rec["days"]:]
        m = market[-len(c):]
        br = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
        mr = [m[i] / m[i - 1] - 1 for i in range(1, len(m))]
        beta = statistics.covariance(br, mr) / statistics.variance(mr)
        resid = statistics.pstdev([x - beta * y for x, y in zip(br, mr)])
        field.append((b["ret"], beta, resid))
    return field


def window_starts(market: engine.Market, first: str, last: str, n: int, stride: int) -> list[int]:
    idx = [i for i, d in enumerate(market.dates) if first <= d <= last and i + n <= len(market.dates)]
    return idx[::stride]


def arnav_moves(market, starts, n) -> dict[int, float]:
    cache = data.CACHE.parent / f"arnav_moves_{n}_{market.dates[starts[0]]}_{market.dates[starts[-1]]}_{len(starts)}.json"
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}
    out = {}
    for i in starts:
        lo = max(0, i - ARNAV_WARM)
        res = engine.run(engine.load_agent(ARNAV), market, market.dates[lo], market.dates[i + n - 1])
        c = res["curve"]
        base = c[-n - 1] if len(c) > n else engine.START_CASH
        out[i] = c[-1] / base - 1
    cache.write_text(json.dumps(out))
    return out


def qqq_moves(market, starts, n) -> dict[int, float]:
    """Close-to-close QQQ move over the window (prior close -> last session close)."""
    pos = {b["ts"]: b["close"] for b in market.bars["QQQ"]}
    return {i: pos[market.dates[i + n - 1]] / pos[market.dates[i - 1]] - 1 for i in starts}


def load_spec(spec: str):
    """'path' or 'path:NAME=value,NAME=value' — overrides module constants for sweeps."""
    path, _, over = spec.partition(":")
    overrides = {k: eval(v, {}) for k, v in (kv.split("=", 1) for kv in over.split(",") if kv)}  # noqa: S307 — local CLI

    def factory():
        fn = engine.load_agent(ROOT / path)
        fn.__globals__.update(overrides)
        return fn
    return factory


def evaluate(spec, market, starts, n, arnav, qqq, board):
    rows = []
    factory = load_spec(spec)
    for i in starts:
        res = engine.run(factory(), market, market.dates[i], market.dates[i + n - 1])
        rows.append((i, res))
    rets = [r["ret"] for _, r in rows]

    def p(cond):
        return sum(1 for c in cond if c) / len(rows)

    beat = [r["ret"] > (1 + board["arnav"]) * (1 + arnav[i]) - 1 for i, r in rows]
    rng = random.Random(7)
    points = prize = first = 0.0
    for (i, r), ok in zip(rows, beat):
        if not ok:
            continue  # entrants below Arnav hold no prize or points position
        for _ in range(DRAWS):
            above = sum(
                1 for now, b, sd in board["field"]
                if (1 + now) * (1 + b * qqq[i] + rng.gauss(0.0, sd * n ** 0.5)) - 1 > r["ret"]
            )
            points += above < 10
            prize += above < 3
            first += above == 0
    rank = {"rank10": points / DRAWS, "rank3": prize / DRAWS, "rank1": first / DRAWS}
    q = statistics.quantiles(rets, n=10)
    return {
        "agent": Path(spec.partition(":")[0]).stem + (":" + spec.partition(":")[2] if ":" in spec else ""), "windows": len(rows), "mean": statistics.fmean(rets), "sd": statistics.pstdev(rets),
        "p10": q[0], "median": statistics.median(rets), "p90": q[-1], "worst": min(rets),
        "p_pos": p(x > 0 for x in rets), "p_beat_arnav": p(beat),
        "p_points": rank["rank10"] / len(rows), "p_prize": rank["rank3"] / len(rows), "p_first": rank["rank1"] / len(rows),
        "worst_mdd": max(r["mdd"] for _, r in rows), "peak_gross": max(r["peak_gross"] for _, r in rows),
        "max_conc_streak": max(r["max_conc_streak"] for _, r in rows), "errors": sum(r["errors"] for _, r in rows),
        "max_runtime": max(r["max_runtime"] for _, r in rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agents", nargs="+")
    ap.add_argument("--sessions", type=int, default=15)
    ap.add_argument("--first", default="2013-06-01")
    ap.add_argument("--last", default="2026-12-31")
    ap.add_argument("--stride", type=int, default=5)
    args = ap.parse_args()

    market = engine.Market(data.load())
    board = board_now()
    starts = window_starts(market, args.first, args.last, args.sessions, args.stride)
    print(f"{len(starts)} windows of {args.sessions} sessions, {market.dates[starts[0]]} .. {market.dates[starts[-1]]}")
    print(f"board {board['as_of']}: arnav {board['arnav']*100:+.2f}%  #1 {board['rank1']*100:+.2f}%  "
          f"#3 {board['rank3']*100:+.2f}%  #10 {board['rank10']*100:+.2f}%\n")
    arnav = arnav_moves(market, starts, args.sessions)
    qqq = qqq_moves(market, starts, args.sessions)

    cols = ["mean", "sd", "p10", "median", "p90", "worst", "p_pos", "p_beat_arnav", "p_points", "p_prize", "p_first", "worst_mdd"]
    print(f"{'agent':60s}" + "".join(f"{c:>13s}" for c in cols) + "   safety")
    for a in args.agents:
        r = evaluate(a, market, starts, args.sessions, arnav, qqq, board)
        cells = "".join(f"{r[c]*100:12.1f}%" for c in cols)
        safety = (f"gross {r['peak_gross']:.2f}x  conc-run {r['max_conc_streak']}d  "
                  f"err {r['errors']}  {r['max_runtime']*1000:.0f}ms")
        print(f"{r['agent'][:60]:60s}{cells}   {safety}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
