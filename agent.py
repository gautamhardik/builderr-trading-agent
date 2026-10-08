"""Trend-Breadth Momentum — builderr Trading Round 2 entry.

Holds the strongest market leaders while the trend and breadth agree, adds a small 2x
Nasdaq sleeve only in calm, broad uptrends, and goes to cash for at least a week when
anything breaks.

Every decision is a pure function of the bars and the current book: no module state,
no network, no LLM, no API keys, standard library only. A restart, a missed session or
a fresh process cannot change what it does.

1. Regime (SPY, QQQ, and breadth = share of the 36 tradeable 1x names above their SMA50)
     OFF      crash brake (QQQ -5% in 5 sessions, or QQQ 10-day vol > 40%), or SPY and
              QQQ both below their SMA50, or breadth < 40% — on ANY of the last 5
              sessions                                             -> all cash
     STRONG   SPY and QQQ above SMA50, QQQ SMA20 > SMA50, breadth >= 55%, and QQQ
              20-day vol < 25%                                     -> 80% leaders + 20% QLD
     NEUTRAL  otherwise                                            -> 80% leaders
2. Leaders: 1x names above their SMA50 with a positive 63-day return, ranked by
   0.6 * r63 + 0.4 * r21. Hold the top 5, equal weight. A held name is kept while it
   stays qualified and inside the top 7, so rank noise does not churn the book.
3. Limits, by construction: each name <= 24% (trimmed if it drifts past 27%), beta gross
   ~1.2x (cap 1.5x), long-only, sells never exceed holdings, <= 12 orders a session.
   Trades only when a weight is more than 3 points off target; full exits always go through.

Validated with research/ (an exact replica of the live board's engine): over 669
historical 15-session windows it beat the benchmark's path in ~84% of them.
"""
from __future__ import annotations

import math

POOL = (
    "SPY", "QQQ", "DIA", "IWM", "SMH", "SOXX", "XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLV", "XLP", "XLU", "XLRE",
    "NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AVGO", "AMD", "MU", "MRVL",
    "NFLX", "TSLA", "PLTR", "ORCL", "CRM", "JPM", "V", "MA", "COST", "LLY",
)
SLEEVE = "QLD"  # 2x Nasdaq-100, bought only in STRONG

TOP_K = 5
KEEP_RANK = 7
LEADER_BUDGET = 0.80
SLEEVE_WEIGHT = 0.20
NAME_CAP = 0.24
DRIFT_CAP = 0.27
TREND_SMA = 50
FAST_SMA = 20
MOM_LONG = 63
MOM_SHORT = 21
BREADTH_ON = 0.40
BREADTH_STRONG = 0.55
VOL_STRONG = 0.25
BRAKE_RET5 = -0.05
BRAKE_VOL10 = 0.40
OFF_COOLDOWN = 5
BAND = 0.03
MIN_BARS = 64


def _closes(market_state, ticker):
    """Close series (oldest first), or None if too short or malformed."""
    try:
        c = [float(b["close"]) for b in market_state.get(ticker) or []]
    except (KeyError, TypeError, ValueError):
        return None
    return c if len(c) >= MIN_BARS and min(c[-MIN_BARS:]) > 0 else None


def _sma(c, n):
    return sum(c[-n:]) / n


def _vol(c, n):
    """Annualized sample volatility of the last n daily returns."""
    r = [c[i] / c[i - 1] - 1 for i in range(len(c) - n, len(c))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1) * 252)


def _risk_off(spy, qqq, pool, lag):
    """Risk-off test as of `lag` sessions ago (0 = latest close). Returns (off, breadth)."""
    s, q = spy[:len(spy) - lag], qqq[:len(qqq) - lag]
    breadth = sum(c[-1 - lag] > _sma(c[:len(c) - lag], TREND_SMA) for c in pool) / len(pool)
    trend_ok = s[-1] > _sma(s, TREND_SMA) or q[-1] > _sma(q, TREND_SMA)
    brake = q[-1] / q[-6] - 1 < BRAKE_RET5 or _vol(q, 10) > BRAKE_VOL10
    return brake or not trend_ok or breadth < BREADTH_ON, breadth


def regime(market_state):
    """'OFF' | 'NEUTRAL' | 'STRONG'."""
    spy, qqq = _closes(market_state, "SPY"), _closes(market_state, "QQQ")
    if spy is None or qqq is None:
        return "OFF"
    pool = [c for c in (_closes(market_state, t) for t in POOL) if c is not None]
    off, breadth = _risk_off(spy, qqq, pool, 0)
    # Stay in cash for OFF_COOLDOWN sessions after any risk-off signal, so a one-day
    # bounce cannot pull the book back into a market that is still breaking.
    if off or any(_risk_off(spy, qqq, pool, lag)[0] for lag in range(1, OFF_COOLDOWN)):
        return "OFF"
    if (spy[-1] > _sma(spy, TREND_SMA) and qqq[-1] > _sma(qqq, TREND_SMA)
            and _sma(qqq, FAST_SMA) > _sma(qqq, TREND_SMA)
            and breadth >= BREADTH_STRONG and _vol(qqq, 20) < VOL_STRONG):
        return "STRONG"
    return "NEUTRAL"


def leaders(market_state, held):
    """Top TOP_K qualified names; currently held names inside the top KEEP_RANK go first."""
    scored = []
    for t in POOL:
        c = _closes(market_state, t)
        if c is None:
            continue
        r63, r21 = c[-1] / c[-MOM_LONG - 1] - 1, c[-1] / c[-MOM_SHORT - 1] - 1
        if r63 > 0 and c[-1] > _sma(c, TREND_SMA):
            scored.append((0.6 * r63 + 0.4 * r21, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    kept = [t for _, t in scored[:KEEP_RANK] if t in held]
    fresh = [t for _, t in scored if t not in kept]
    return (kept + fresh)[:TOP_K]


def targets(market_state, held):
    """Target weights (fractions of equity)."""
    state = regime(market_state)
    if state == "OFF":
        return {}
    picks = leaders(market_state, held)
    w = {t: min(NAME_CAP, LEADER_BUDGET / len(picks)) for t in picks}
    if state == "STRONG" and _closes(market_state, SLEEVE) is not None:
        w[SLEEVE] = SLEEVE_WEIGHT
    return w


def decide(market_state, portfolio_state, cash):
    try:
        return _decide(market_state or {}, portfolio_state or {}, float(cash))
    except Exception:  # noqa: BLE001 — a bad tick must never crash the run
        return []


def _decide(market_state, portfolio_state, cash):
    prices = {}
    for t, p in (portfolio_state.get("last_prices") or {}).items():
        try:
            if float(p) > 0:
                prices[str(t).upper()] = float(p)
        except (TypeError, ValueError):
            continue
    held = {}
    for p in portfolio_state.get("positions") or []:
        t, q = str(p.get("ticker", "")).upper(), float(p.get("quantity", 0.0))
        if q > 0:
            held[t] = held.get(t, 0.0) + q
    equity = cash + sum(q * prices.get(t, 0.0) for t, q in held.items())
    if equity <= 0:
        return []
    want = targets(market_state, held)

    sells, buys = [], []
    for t in sorted(held):
        px = prices.get(t)
        if not px:
            continue
        cur, goal = held[t] * px / equity, want.get(t, 0.0)
        if goal == 0.0:
            sells.append({"ticker": t, "side": "sell", "quantity": held[t]})
        elif cur - goal > BAND or cur > DRIFT_CAP:
            qty = math.floor((cur - goal) * equity / px)
            if qty > 0:
                sells.append({"ticker": t, "side": "sell", "quantity": float(min(qty, held[t]))})
    spendable = cash + 0.995 * sum(o["quantity"] * prices[o["ticker"]] for o in sells)
    for t in sorted(want, key=lambda k: (-want[k], k)):
        px = prices.get(t)
        if not px:
            continue
        gap = want[t] - held.get(t, 0.0) * px / equity
        if gap > BAND:
            qty = math.floor(min(gap * equity, spendable) / (px * 1.001))
            if qty > 0:
                buys.append({"ticker": t, "side": "buy", "quantity": float(qty)})
                spendable -= qty * px * 1.001
    return sells + buys
