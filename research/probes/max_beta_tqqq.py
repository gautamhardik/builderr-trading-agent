"""Probe, not a candidate: hold the beta cap (≈50% TQQQ = 1.5x) at all times.

Measures the raw upside and downside of maximum allowed market exposure over a short
window, so we can see what aggression alone buys before any signal is added.
"""

TARGET = 0.49  # just under 1.5x beta gross at 3x


def decide(market_state, portfolio_state, cash):
    price = portfolio_state["last_prices"].get("TQQQ")
    if not price:
        return []
    held = {p["ticker"]: p["quantity"] for p in portfolio_state["positions"]}
    equity = cash + sum(q * portfolio_state["last_prices"].get(t, 0.0) for t, q in held.items())
    delta = int(TARGET * equity / price) - held.get("TQQQ", 0.0)
    if abs(delta) * price < 0.03 * equity:
        return []
    return [{"ticker": "TQQQ", "side": "buy" if delta > 0 else "sell", "quantity": abs(delta)}]
