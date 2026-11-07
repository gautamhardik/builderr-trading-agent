"""Apex All-Weather v3 — Dual-Gear Regime & Quality Rotation Agent."""
from __future__ import annotations

import math

POOL = (
    "SPY", "QQQ", "DIA", "IWM", "SMH", "SOXX", "XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLV", "XLP", "XLU", "XLRE",
    "NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AVGO", "AMD", "MU", "MRVL",
    "NFLX", "TSLA", "PLTR", "ORCL", "CRM", "JPM", "V", "MA", "COST", "LLY",
)
DEFENSIVE_POOL = ("COST", "XLP", "XLU", "XLV", "MA", "V", "LLY", "XLRE", "XLF")
BETA_3X = {"TQQQ", "SOXL", "UPRO", "SPXL", "TNA", "FAS", "TECL", "LABU", "CURE", "DRN", "UDOW", "NAIL"}
BETA_2X = {"QLD", "SSO", "DDM", "ROM", "UWM", "AGQ"}

TOP_K = 3
KEEP_RANK = 6
LEADER_WEIGHT = 0.245
QUALITY_WEIGHT = 0.225
STRONG_SLEEVE_WEIGHT = 0.215
CONSTRUCTIVE_SLEEVE_WEIGHT = 0.200
DEFENSIVE_WEIGHT = 0.225
NAME_CAP = 0.250
DRIFT_CAP = 0.285
GROSS_LIMIT = 1.40
BAND = 0.035
STOP_LOSS_PCT = 0.050
MIN_BARS = 64


def _beta(ticker: str) -> float:
    if ticker in BETA_3X:
        return 3.0
    if ticker in BETA_2X:
        return 2.0
    return 1.0


def _closes(market_state: dict, ticker: str) -> list[float] | None:
    try:
        c = [float(b["close"]) for b in market_state.get(ticker) or []]
    except (KeyError, TypeError, ValueError):
        return None
    return c if len(c) >= MIN_BARS and min(c[-MIN_BARS:]) > 0 else None


def _sma(c: list[float], n: int) -> float:
    return sum(c[-n:]) / n


def _vol(c: list[float], n: int) -> float:
    r = [c[i] / c[i - 1] - 1.0 for i in range(len(c) - n, len(c))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / max(1, n - 1) * 252.0)


def defensive_picks(market_state: dict) -> list[str]:
    """Select tradeable Round 2 low-volatility sanctuaries that are actively trending up."""
    spy = _closes(market_state, "SPY")
    if spy is not None:
        r1_spy = spy[-1] / spy[-2] - 1.0
        r5_spy = spy[-1] / spy[-6] - 1.0
        vol10_spy = _vol(spy, 10)
        # In a systemic S&P 500 waterfall crash (like March 2020), stay 100% Cash
        if vol10_spy > 0.34 or r5_spy < -0.045 or r1_spy < -0.025:
            return []

    scored = []
    for t in DEFENSIVE_POOL:
        c = _closes(market_state, t)
        if c is None:
            continue
        sma5, sma10, sma20, sma50 = _sma(c, 5), _sma(c, 10), _sma(c, 20), _sma(c, 50)
        r63 = c[-1] / c[-64] - 1.0
        r21 = c[-1] / c[-22] - 1.0
        r5 = c[-1] / c[-6] - 1.0
        vol20 = _vol(c, 20)
        if (
            c[-1] > sma10 >= sma20 > sma50
            and c[-1] >= sma5 * 0.99
            and r21 > 0.030
            and r63 > 0.0
            and r5 > -0.012
            and vol20 < 0.30
        ):
            score = (0.40 * r63 + 0.60 * r21) / max(vol20, 0.15)
            scored.append((score, t))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:4]]


def regime(market_state: dict) -> str:
    """
    4-State All-Weather Engine:
    - STRONG: Both SPY & QQQ > SMA20 > SMA50 in low volatility -> 3 Trend Leaders + 3x Sleeve
    - CONSTRUCTIVE: Both SPY & QQQ > SMA20 > SMA50 in moderate volatility -> 3 Trend Leaders + 2x QLD
    - QUALITY_ROTATION: Tech/QQQ broken, but SPY > SMA200 & low-vol non-tech leaders trending -> 4 Quality Leaders, 0% Leverage
    - DEFENSIVE_ROTATION: Systemic market crash -> 100% Cash (or strict low-vol sanctuaries)
    """
    spy, qqq = _closes(market_state, "SPY"), _closes(market_state, "QQQ")
    if spy is None or qqq is None:
        return "DEFENSIVE_ROTATION"
    pool = [c for c in (_closes(market_state, t) for t in POOL) if c is not None]
    if not pool:
        return "DEFENSIVE_ROTATION"

    breadth50 = sum(c[-1] > _sma(c, 50) for c in pool) / len(pool)
    breadth20 = sum(c[-1] > _sma(c, 20) for c in pool) / len(pool)
    breadth = max(breadth50, breadth20)

    r1_qqq = qqq[-1] / qqq[-2] - 1.0
    r5_qqq = qqq[-1] / qqq[-6] - 1.0
    sma5_qqq = _sma(qqq, 5)
    sma10_qqq = _sma(qqq, 10)
    sma20_qqq = _sma(qqq, 20)
    sma30_qqq = _sma(qqq, 30)
    sma50_qqq = _sma(qqq, 50)
    vol20_qqq = _vol(qqq, 20)
    vol10_qqq = _vol(qqq, 10)

    r1_spy = spy[-1] / spy[-2] - 1.0
    r5_spy = spy[-1] / spy[-6] - 1.0
    sma20_spy = _sma(spy, 20)
    sma50_spy = _sma(spy, 50)
    sma200_spy = _sma(spy, 200) if len(spy) >= 200 else sma50_spy
    vol10_spy = _vol(spy, 10)

    # 1. SYSTEMIC MARKET CRASH -> DEFENSIVE_ROTATION
    systemic_crash = (
        vol10_spy > 0.32
        or vol10_qqq > 0.45
        or r5_spy < -0.042
        or r1_spy <= -0.024
        or spy[-1] < sma200_spy * 0.98
    )
    if systemic_crash:
        return "DEFENSIVE_ROTATION"

    # 2. BOTH SPY AND QQQ IN UPTREND -> STRONG or CONSTRUCTIVE
    both_uptrend = (
        spy[-1] > sma50_spy
        and qqq[-1] > sma50_qqq
        and qqq[-1] > sma20_qqq
        and r5_qqq > -0.025
        and r1_qqq > -0.020
    )
    if both_uptrend:
        stacked_qqq = (qqq[-1] > sma5_qqq > sma20_qqq > sma50_qqq) and (r5_qqq > 0.0)
        if (
            vol20_qqq < 0.25
            and vol10_qqq < 0.27
            and ((sma10_qqq > sma30_qqq and breadth50 >= 0.45) or (stacked_qqq and breadth >= 0.35))
        ):
            return "STRONG"
        if vol20_qqq < 0.30 and vol10_qqq < 0.30 and (spy[-1] > sma20_spy or breadth >= 0.40):
            return "CONSTRUCTIVE"

    # 3. TECH / QQQ BROKEN -> Check if Quality Non-Tech Rotation is active
    if defensive_picks(market_state):
        return "QUALITY_ROTATION"

    return "DEFENSIVE_ROTATION"


def leaders(market_state: dict, held: set[str] | dict) -> list[str]:
    """Select top momentum leaders when QQQ & SPY are in a confirmed uptrend."""
    qqq = _closes(market_state, "QQQ")
    if qqq is None:
        return []
    r5_qqq = qqq[-1] / qqq[-6] - 1.0

    scored = []
    for t in POOL:
        c = _closes(market_state, t)
        if c is None:
            continue
        sma10, sma20, sma50 = _sma(c, 10), _sma(c, 20), _sma(c, 50)
        if c[-1] <= sma50 or c[-1] <= sma20:
            continue
        r63 = c[-1] / c[-64] - 1.0
        r21 = c[-1] / c[-22] - 1.0
        r5 = c[-1] / c[-6] - 1.0
        if r63 <= 0.0 or r21 <= 0.0 or r5 <= -0.025:
            continue
        if t not in held and c[-1] < sma10 * 0.99:
            continue

        vol20 = _vol(c, 20)
        vol_pen = max(1.0, vol20 / 0.45)
        raw_score = (0.50 * r63 + 0.35 * r21 + 0.15 * (r5 - r5_qqq)) / vol_pen

        t_bars = market_state.get(t) or []
        high20 = max(float(b.get("high", b["close"])) for b in t_bars[-20:]) if t_bars else c[-1]
        if c[-1] >= 0.97 * high20:
            raw_score *= 1.15

        if raw_score > 0:
            scored.append((raw_score, t))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top_keep = [t for _, t in scored[:KEEP_RANK]]
    kept = [
        t
        for t in top_keep
        if t in held
        and _closes(market_state, t) is not None
        and _closes(market_state, t)[-1] > _sma(_closes(market_state, t), 20)
    ]
    fresh = [t for _, t in scored if t not in kept]
    return (kept + fresh)[:TOP_K]


def targets(market_state: dict, held: set[str] | dict) -> dict[str, float]:
    state = regime(market_state)
    if state in ("DEFENSIVE_ROTATION", "QUALITY_ROTATION"):
        dp = defensive_picks(market_state)
        return {t: QUALITY_WEIGHT for t in dp}

    picks = leaders(market_state, held)
    w = {t: LEADER_WEIGHT for t in picks}
    qqq = _closes(market_state, "QQQ")

    if state == "STRONG":
        smh = _closes(market_state, "SMH")
        soxl = _closes(market_state, "SOXL")
        tqqq = _closes(market_state, "TQQQ")
        soxl_ok = False
        r10_smh, r10_qqq = 0.0, 0.0
        if soxl is not None and smh is not None and qqq is not None:
            r10_smh = smh[-1] / smh[-11] - 1.0
            r10_qqq = qqq[-1] / qqq[-11] - 1.0
            if r10_smh > r10_qqq * 1.01 and _vol(smh, 10) < 0.36 and smh[-1] > _sma(smh, 20):
                soxl_ok = True

        sleeve = None
        if "SOXL" in held and soxl_ok:
            sleeve = "SOXL"
        elif "TQQQ" in held and tqqq is not None and not (soxl_ok and r10_smh > r10_qqq + 0.03):
            sleeve = "TQQQ"
        elif soxl_ok:
            sleeve = "SOXL"
        elif tqqq is not None:
            sleeve = "TQQQ"
        elif soxl is not None:
            sleeve = "SOXL"

        if sleeve is not None:
            w[sleeve] = STRONG_SLEEVE_WEIGHT
        elif _closes(market_state, "QLD") is not None:
            w["QLD"] = 0.245

    elif state == "CONSTRUCTIVE":
        if _closes(market_state, "QLD") is not None:
            w["QLD"] = CONSTRUCTIVE_SLEEVE_WEIGHT
        elif _closes(market_state, "SSO") is not None:
            w["SSO"] = CONSTRUCTIVE_SLEEVE_WEIGHT

    gross = sum(weight * _beta(ticker) for ticker, weight in w.items())
    if gross > GROSS_LIMIT:
        scale = GROSS_LIMIT / gross
        w = {ticker: weight * scale for ticker, weight in w.items()}

    return w


def decide(market_state: dict, portfolio_state: dict, cash: float) -> list[dict]:
    try:
        return _decide(market_state or {}, portfolio_state or {}, float(cash))
    except Exception:
        return []


def _decide(market_state: dict, portfolio_state: dict, cash: float) -> list[dict]:
    prices = {}
    for t, p in (portfolio_state.get("last_prices") or {}).items():
        try:
            if float(p) > 0:
                prices[str(t).upper()] = float(p)
        except (TypeError, ValueError):
            continue

    held = {}
    avg_costs = {}
    for p in portfolio_state.get("positions") or []:
        t = str(p.get("ticker", "")).upper()
        q = float(p.get("quantity", 0.0))
        ac = float(p.get("avg_cost", 0.0) or 0.0)
        if q > 0:
            held[t] = held.get(t, 0.0) + q
            if ac > 0:
                avg_costs[t] = ac

    equity = cash + sum(q * prices.get(t, 0.0) for t, q in held.items())
    if equity <= 0:
        return []

    want = targets(market_state, held)
    current_gross_beta = sum(
        held.get(t, 0.0) * prices.get(t, 0.0) * _beta(t) for t in held
    ) / equity

    sells, buys = [], []
    stopped_tickers = set()

    for t in sorted(held):
        px = prices.get(t)
        if not px:
            continue
        cur = held[t] * px / equity
        goal = want.get(t, 0.0)
        b_mult = _beta(t)

        ac = avg_costs.get(t, 0.0)
        c_series = _closes(market_state, t)
        hit_stop = (ac > 0 and px < ac * (1.0 - STOP_LOSS_PCT)) or (
            c_series is not None and px < _sma(c_series, 20) * 0.985
        )
        if hit_stop:
            sells.append({"ticker": t, "side": "sell", "quantity": float(held[t])})
            stopped_tickers.add(t)
            continue

        # Retain incumbent non-leveraged quality/trend holdings if still above SMA20 & SMA50
        # when in QUALITY_ROTATION to prevent unnecessary turnover
        if (
            goal == 0.0
            and b_mult == 1.0
            and t in DEFENSIVE_POOL
            and c_series is not None
            and px > _sma(c_series, 20) > _sma(c_series, 50)
            and len(want) >= 3
        ):
            continue

        effective_band = 0.010 if (b_mult >= 3.0 and current_gross_beta > 1.42) else BAND
        effective_cap = 0.230 if b_mult >= 3.0 else DRIFT_CAP

        if goal == 0.0:
            sells.append({"ticker": t, "side": "sell", "quantity": float(held[t])})
        elif cur - goal > effective_band or cur > effective_cap:
            qty = math.floor((cur - goal) * equity / px)
            if qty > 0:
                sells.append({"ticker": t, "side": "sell", "quantity": float(min(qty, held[t]))})

    spendable = cash + 0.995 * sum(o["quantity"] * prices[o["ticker"]] for o in sells)
    for t in sorted(want, key=lambda k: (-want[k], k)):
        if t in stopped_tickers:
            continue
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
