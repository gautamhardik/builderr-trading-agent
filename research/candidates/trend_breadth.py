"""Trend-Breadth Momentum — a balanced, stateless Round 2 agent.

Every decision is a pure function of the bars and the current book, so a restart, a
missed session or a fresh process never changes behaviour.

1. Regime (from SPY / QQQ / breadth of the 36 tradeable 1x names):
     OFF     crash brake (QQQ -5% in 5 sessions, or 10-day vol > 40%), or SPY and QQQ
             both below their 50-day SMA, or breadth < 40%  -> all cash
     NEUTRAL otherwise                                       -> 80% in leaders
     STRONG  SPY and QQQ above SMA50, QQQ SMA20 > SMA50, breadth >= 55%, QQQ 20-day
             vol < 25%                                       -> 80% leaders + 20% QLD
2. Leaders: 1x names above their SMA50 with positive 63-day return, ranked by
   (0.6 * r63 + 0.4 * r21) / vol63. Hold the top 5; a held name is kept while it stays
   qualified and inside the top 7, so rank noise does not churn the book.
3. Sizing: inverse-volatility within the leader budget, each name capped at 24%.
4. Safety: beta gross <= 1.2x by construction; trades only when a target moves more than
   3% of equity, except full exits, which always go through; a name drifting above 27% is
   trimmed. Long-only, stdlib only, no network.
"""
from __future__ import annotations

import math

POOL = (
    "SPY", "QQQ", "DIA", "IWM", "SMH", "SOXX", "XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLV", "XLP", "XLU", "XLRE",
    "NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AVGO", "AMD", "MU", "MRVL",
    "NFLX", "TSLA", "PLTR", "ORCL", "CRM", "JPM", "V", "MA", "COST", "LLY",
)
SLEEVE = "QLD"
BETA = {"QLD": 2.0, "SSO": 2.0, "TQQQ": 3.0, "SOXL": 3.0, "UPRO": 3.0, "SPXL": 3.0}

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
OFF_COOLDOWN = 1       # sessions any risk-off signal keeps the book in cash (1 = only while firing)
BAND = 0.03
MIN_BARS = 64
VOL_ADJUSTED_SCORE = False  # rank by momentum / vol (else raw momentum)
INVERSE_VOL_WEIGHTS = False  # size by 1/vol (else equal weight)
NEUTRAL_BUDGET = 0.80
OFF_IF_EITHER = False  # go to cash when SPY or QQQ breaks trend (else only when both do)
NAME_STOP = 0.0        # drop a name this far below its 20-day high (0 = off)
CAUTION = False        # halve exposure while QQQ is below a falling 20-day SMA
CAUTION_SCALE = 0.5
SEMIS = {"SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL"}
SEMIS_MAX = 5          # max semiconductor names among the picks (5 = no cap)


def _closes(market_state, t):
    bars = market_state.get(t) or []
    try:
        c = [float(b["close"]) for b in bars]
    except (KeyError, TypeError, ValueError):
        return None
    return c if len(c) >= MIN_BARS and c[-1] > 0 and min(c[-MIN_BARS:]) > 0 else None


def _sma(c, n):
    return sum(c[-n:]) / n


def _vol(c, n):
    r = [c[i] / c[i - 1] - 1 for i in range(len(c) - n, len(c))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1) * 252)


def _off(spy, qqq, pool, lag):
    """Risk-off test as of `lag` sessions ago (0 = latest close)."""
    end = len(qqq) - lag
    s, q = spy[:len(spy) - lag], qqq[:end]
    breadth = sum(c[-1 - lag] > _sma(c[:len(c) - lag], TREND_SMA) for c in pool) / len(pool)
    spy_up, qqq_up = s[-1] > _sma(s, TREND_SMA), q[-1] > _sma(q, TREND_SMA)
    brake = q[-1] / q[-6] - 1 < BRAKE_RET5 or _vol(q, 10) > BRAKE_VOL10
    trend_ok = (spy_up and qqq_up) if OFF_IF_EITHER else (spy_up or qqq_up)
    return brake or not trend_ok or breadth < BREADTH_ON, breadth


def regime(market_state):
    spy, qqq = _closes(market_state, "SPY"), _closes(market_state, "QQQ")
    if spy is None or qqq is None:
        return "OFF", 0.0
    pool = [c for c in (_closes(market_state, t) for t in POOL) if c is not None]
    off, breadth = _off(spy, qqq, pool, 0)
    # Stay in cash for OFF_COOLDOWN sessions after any risk-off signal, so a one-day
    # bounce cannot pull the book back into a market that is still breaking.
    if off or any(_off(spy, qqq, pool, lag)[0] for lag in range(1, OFF_COOLDOWN)):
        return "OFF", breadth
    spy_up, qqq_up = spy[-1] > _sma(spy, TREND_SMA), qqq[-1] > _sma(qqq, TREND_SMA)
    if (spy_up and qqq_up and _sma(qqq, FAST_SMA) > _sma(qqq, TREND_SMA)
            and breadth >= BREADTH_STRONG and _vol(qqq, 20) < VOL_STRONG):
        return "STRONG", breadth
    if CAUTION and qqq[-1] < _sma(qqq, FAST_SMA) and _sma(qqq, FAST_SMA) < _sma(qqq[:-5], FAST_SMA):
        return "CAUTION", breadth
    return "NEUTRAL", breadth


def leaders(market_state, held):
    scored = []
    for t in POOL:
        c = _closes(market_state, t)
        if c is None:
            continue
        r63, r21 = c[-1] / c[-MOM_LONG - 1] - 1, c[-1] / c[-MOM_SHORT - 1] - 1
        if r63 <= 0 or c[-1] <= _sma(c, TREND_SMA):
            continue
        if NAME_STOP and c[-1] < (1 - NAME_STOP) * max(c[-20:]):
            continue  # stateless trailing stop: too far off its 20-day high
        vol = _vol(c, MOM_LONG)
        mom = 0.6 * r63 + 0.4 * r21
        scored.append((mom / max(vol, 1e-6) if VOL_ADJUSTED_SCORE else mom, t, vol))
    scored.sort(key=lambda x: (-x[0], x[1]))
    kept = [s for i, s in enumerate(scored[:KEEP_RANK]) if s[1] in held]
    fresh = [s for s in scored if s[1] not in {k[1] for k in kept}]
    picks, semis = [], 0
    for s in kept + fresh:
        if s[1] in SEMIS:
            if semis >= SEMIS_MAX:
                continue  # one crowded trade, not five: cap the semiconductor cluster
            semis += 1
        picks.append(s)
        if len(picks) == TOP_K:
            break
    return picks


def targets(market_state, held):
    state, _ = regime(market_state)
    if state == "OFF":
        return {}
    picks = leaders(market_state, held)
    inv = {t: (1.0 / max(vol, 1e-6) if INVERSE_VOL_WEIGHTS else 1.0) for _, t, vol in picks}
    total = sum(inv.values())
    budget = {"STRONG": LEADER_BUDGET, "NEUTRAL": NEUTRAL_BUDGET}.get(state, NEUTRAL_BUDGET * CAUTION_SCALE)
    w = {t: min(NAME_CAP, budget * v / total) for t, v in inv.items()} if total else {}
    if state == "STRONG" and _closes(market_state, SLEEVE) is not None:
        w[SLEEVE] = SLEEVE_WEIGHT
    return w


def decide(market_state, portfolio_state, cash):
    try:
        return _decide(market_state or {}, portfolio_state or {}, float(cash))
    except Exception:  # noqa: BLE001 — a bad tick must never crash the run
        return []


def _decide(market_state, portfolio_state, cash):
    prices = {str(t).upper(): float(p) for t, p in (portfolio_state.get("last_prices") or {}).items() if p}
    held = {}
    for p in portfolio_state.get("positions") or []:
        q = float(p.get("quantity", 0.0))
        if q > 0:
            held[str(p["ticker"]).upper()] = held.get(str(p["ticker"]).upper(), 0.0) + q
    equity = cash + sum(q * prices.get(t, 0.0) for t, q in held.items())
    if equity <= 0:
        return []
    want = targets(market_state, held)

    sells, buys = [], []
    for t in sorted(held):
        px = prices.get(t)
        if not px:
            continue
        cur = held[t] * px / equity
        goal = want.get(t, 0.0)
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
