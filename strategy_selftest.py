"""Strategy-level checks for agent.py (Apex Sprint v2).

No network, no private engine, no third-party packages. These catch contract,
cap, and regime bugs before submission.

Run:
    python strategy_selftest.py
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from pathlib import Path

import agent

UNIVERSE = agent.POOL + ("QLD", "SSO", "TQQQ", "SOXL")
BETA = {"QLD": 2.0, "SSO": 2.0, "TQQQ": 3.0, "SOXL": 3.0}


def bars(returns: list[float], start: float = 100.0) -> list[dict]:
    out, px, d = [], start, date(2024, 1, 1)
    for r in returns:
        px *= 1.0 + r
        out.append({"ts": d.isoformat(), "open": px, "high": px * 1.01, "low": px * 0.99, "close": px,
                    "volume": 1_000_000})
        d += timedelta(days=1)
    return out


def market(kind: str, n: int = 140) -> dict[str, list[dict]]:
    if kind == "risk_off":
        return {t: bars([-0.003] * n) for t in UNIVERSE}
    if kind == "high_vol":
        m = {t: bars([0.002] * n) for t in UNIVERSE}
        m["QQQ"] = bars([0.035, -0.03] * (n // 2))
        return m
    m = {t: bars([0.001] * n) for t in UNIVERSE}  # calm, broad uptrend
    for t in ("SMH", "NVDA", "XLK"):
        m[t] = bars([0.004] * n)
    for t in ("AAPL", "META"):
        m[t] = bars([0.0025] * n)
    m["QQQ"] = bars([0.0015] * n)
    m["QLD"] = bars([0.003] * n)
    m["TQQQ"] = bars([0.0045] * n)
    m["SOXL"] = bars([0.005] * n)
    return m


def book(m, weights=None, cash=100_000.0):
    prices = {t: b[-1]["close"] for t, b in m.items()}
    positions = [{"ticker": t, "quantity": w * 100_000.0 / prices[t], "avg_cost": prices[t]}
                 for t, w in (weights or {}).items()]
    return {"cash": cash, "positions": positions, "last_prices": prices}


def beta_gross(weights):
    return sum(w * BETA.get(t, 1.0) for t, w in weights.items())


def test_empty_data_returns_no_orders():
    assert agent.decide({}, {"cash": 100_000, "positions": [], "last_prices": {}}, 100_000) == []
    assert agent.decide(None, None, 100_000) == []


def test_insufficient_history_holds_nothing():
    short = market("risk_on", n=40)
    assert agent.targets(short, {}) == {}
    assert agent.decide(short, book(short), 100_000.0) == []


def test_risk_off_goes_flat():
    m = market("risk_off")
    assert agent.regime(m) == "DEFENSIVE_ROTATION"
    orders = agent.decide(m, book(m, {"SPY": 0.2, "NVDA": 0.2}, cash=60_000.0), 60_000.0)
    assert orders and all(o["side"] == "sell" for o in orders)
    assert {o["ticker"] for o in orders} == {"SPY", "NVDA"}


def test_strong_regime_buys_leaders_and_sleeve():
    m = market("risk_on")
    assert agent.regime(m) == "STRONG"
    w = agent.targets(m, {})
    assert len(w) >= 3, w
    # Holds leaders and a leveraged sleeve (SOXL or TQQQ)
    assert any(s in w for s in ("SOXL", "TQQQ", "QLD")), w


def test_high_vol_disables_leverage():
    w = agent.targets(market("high_vol"), {})
    assert not set(w) & set(BETA), w


def test_price_confirmation_unlock_after_a_crash():
    calm = [0.002] * 130
    m = {t: bars(calm) for t in UNIVERSE}
    # -7% slide, then an immediate sharp rebound with Close > SMA5 and R1 > 0
    m["QQQ"] = bars(calm[:-8] + [-0.025] * 3 + [0.035] * 2)
    reg = agent.regime(m)
    # The bot must NOT be frozen in cash: price confirmation unlock activates SNAPBACK or CONSTRUCTIVE
    assert reg in ("SNAPBACK", "CONSTRUCTIVE", "STRONG"), reg


def test_caps_hold():
    for kind in ("risk_off", "high_vol", "risk_on"):
        w = agent.targets(market(kind), {})
        assert all(v <= agent.NAME_CAP + 1e-9 or t in BETA for t, v in w.items()), (kind, w)
        assert sum(w.values()) <= 1.0 + 1e-9, (kind, w)
        assert beta_gross(w) <= 1.48, (kind, w)


def test_drifted_name_is_trimmed():
    m = market("risk_on")
    orders = agent.decide(m, book(m, {"NVDA": 0.29}, cash=71_000.0), 71_000.0)
    trims = [o for o in orders if o["ticker"] == "NVDA" and o["side"] == "sell"]
    assert trims, orders


def test_orders_are_bounded_fast_and_deterministic():
    m = market("risk_on")
    portfolio = book(m)
    start = time.perf_counter()
    orders = agent.decide(m, portfolio, 100_000.0)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05, f"Took {elapsed:.4f}s > 0.05s"
    assert 0 < len(orders) <= 12, orders
    assert all(o["side"] in {"buy", "sell"} and o["quantity"] > 0 for o in orders)
    assert agent.decide(m, portfolio, 100_000.0) == orders  # stateless: same inputs, same orders
    cost = sum(o["quantity"] * portfolio["last_prices"][o["ticker"]] for o in orders if o["side"] == "buy")
    assert cost <= 100_000.0


def test_sells_never_exceed_holdings():
    m = market("risk_off")
    portfolio = book(m, {"SPY": 0.1234567})
    for o in agent.decide(m, portfolio, 100_000.0):
        assert o["quantity"] <= portfolio["positions"][0]["quantity"] + 1e-9


def test_no_network_or_llm_imports():
    src = Path(agent.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(requests|urllib|http|socket|openai|anthropic)", src, re.M)


def run() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for test in tests:
        test()
    print(f"OK - {len(tests)} strategy checks passed.")


if __name__ == "__main__":
    run()
