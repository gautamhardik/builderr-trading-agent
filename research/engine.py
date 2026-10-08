"""Fast replica of live_runner.run_bot — the engine that actually ranks Round 2.

Same semantics, including the quirks:
  * decide() sees bars strictly BEFORE the session; orders fill at the session OPEN.
  * sells execute before buys; at most 100 orders per decision.
  * buys are clipped to cash, 30% of equity-at-open per name, and 1.5x beta gross.
  * equity is marked at the session close (a held name with no bar that day marks at 0).
Differences are speed only: O(1) price lookups instead of linear scans, plus extra
telemetry (gross / concentration at close, runtime) that run_bot does not report.
"""
from __future__ import annotations

import importlib.util
import math
import time
from bisect import bisect_left
from pathlib import Path

START_CASH = 100_000.0
SLIP_EQUITY = 0.0005
SLIP_LEVERAGED = 0.0010
MAX_NAME_WEIGHT = 0.30
MAX_BETA_GROSS = 1.50
MAX_ORDERS_PER_DECISION = 100
HISTORY_BARS = 300  # the live board keeps ~310 bars per ticker (EVAL_DAYS + WARMUP_DAYS + 30)
BETA_3X = {"TQQQ", "SOXL", "UPRO", "SPXL", "TNA", "FAS", "TECL", "LABU", "CURE", "DRN", "UDOW", "NAIL"}
BETA_2X = {"QLD", "SSO", "DDM", "ROM", "UWM", "AGQ"}


def beta(t: str) -> float:
    return 3.0 if t in BETA_3X else 2.0 if t in BETA_2X else 1.0


def load_agent(path: str | Path):
    """Fresh module per call so module-level state resets, like a new live process."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"agent_{path.stem}_{time.perf_counter_ns()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "AGENT", mod.decide)


class Market:
    def __init__(self, compact: dict[str, list[list]]):
        self.bars = {
            t: [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]
            for t, rows in compact.items()
        }
        self.ts = {t: [b["ts"] for b in rows] for t, rows in self.bars.items()}
        self.dates = sorted({d for ts in self.ts.values() for d in ts})

    def sessions(self, start: str, n: int) -> list[str]:
        i = bisect_left(self.dates, start)
        return self.dates[i:i + n]


def run(decide, market: Market, start: str, end: str, *, history: int = HISTORY_BARS) -> dict:
    eval_dates = [d for d in market.dates if start <= d <= end]
    cash = START_CASH
    positions: dict[str, float] = {}
    avg_cost: dict[str, float] = {}
    curve: list[float] = []
    trades = errors = 0
    peak_gross = peak_conc = max_runtime = 0.0
    conc_streak: dict[str, int] = {}
    max_conc_streak = 0

    for date in eval_dates:
        open_px: dict[str, float] = {}
        close_px: dict[str, float] = {}
        market_state: dict[str, list] = {}
        for t, rows in market.bars.items():
            cut = bisect_left(market.ts[t], date)
            if cut < len(rows) and rows[cut]["ts"] == date:
                open_px[t] = rows[cut]["open"]
                close_px[t] = rows[cut]["close"]
            market_state[t] = rows[max(0, cut - history):cut]
        prior_close = {t: ms[-1]["close"] for t, ms in market_state.items() if ms}
        portfolio_state = {
            "cash": cash,
            "positions": [{"ticker": t, "quantity": q, "avg_cost": avg_cost.get(t, 0.0)}
                          for t, q in positions.items() if q > 0],
            "last_prices": prior_close,
        }
        t0 = time.perf_counter()
        try:
            orders = decide(market_state, portfolio_state, cash) or []
        except Exception:  # noqa: BLE001
            errors += 1
            orders = []
        max_runtime = max(max_runtime, time.perf_counter() - t0)

        normalized = []
        for o in orders[:MAX_ORDERS_PER_DECISION] if isinstance(orders, list) else []:
            try:
                tk = str(o["ticker"]).strip().upper()
                side, qty = o["side"], float(o["quantity"])
            except (KeyError, TypeError, ValueError):
                continue
            if side not in ("buy", "sell") or not math.isfinite(qty) or qty <= 0 or tk not in open_px:
                continue
            normalized.append((tk, side, qty))

        for tk, side, qty in sorted(normalized, key=lambda x: 0 if x[1] == "sell" else 1):
            px = open_px[tk]
            slip = SLIP_LEVERAGED if beta(tk) > 1 else SLIP_EQUITY
            if side == "buy":
                fill = px * (1 + slip)
                equity_at_open = max(cash + sum(positions.get(t, 0.0) * open_px.get(t, 0.0) for t in positions), 1e-9)
                held = positions.get(tk, 0.0)
                concentration_room = max(0.0, MAX_NAME_WEIGHT * equity_at_open - held * fill)
                beta_used = sum(positions.get(t, 0.0) * open_px.get(t, 0.0) * beta(t) for t in positions)
                beta_room = max(0.0, MAX_BETA_GROSS * equity_at_open - beta_used)
                max_notional = min(cash, concentration_room, beta_room / beta(tk))
                qty = min(qty, max_notional / fill if fill > 0 else 0.0)
                if qty <= 0:
                    continue
                avg_cost[tk] = (avg_cost.get(tk, 0.0) * held + fill * qty) / (held + qty) if held + qty > 0 else fill
                positions[tk] = held + qty
                cash -= fill * qty
                trades += 1
            else:
                held = positions.get(tk, 0.0)
                qty = min(qty, held)
                if qty <= 0:
                    continue
                cash += px * (1 - slip) * qty
                positions[tk] = held - qty
                trades += 1

        values = {t: positions.get(t, 0.0) * close_px.get(t, 0.0) for t in positions}
        equity = max(cash + sum(values.values()), 1e-9)
        curve.append(equity)
        peak_gross = max(peak_gross, sum(v * beta(t) for t, v in values.items()) / equity)
        for t, v in values.items():
            frac = v / equity
            peak_conc = max(peak_conc, frac)
            conc_streak[t] = conc_streak.get(t, 0) + 1 if frac >= MAX_NAME_WEIGHT else 0
            max_conc_streak = max(max_conc_streak, conc_streak[t])

    final = curve[-1] if curve else START_CASH
    return {
        "dates": eval_dates, "curve": curve, "ret": final / START_CASH - 1, "trades": trades,
        "errors": errors, "mdd": max_drawdown(curve), "peak_gross": peak_gross, "peak_conc": peak_conc,
        "max_conc_streak": max_conc_streak, "max_runtime": max_runtime,
        "holdings": {t: q for t, q in positions.items() if q > 0}, "cash": cash,
    }


def max_drawdown(curve: list[float]) -> float:
    peak, mdd = -1e18, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd
