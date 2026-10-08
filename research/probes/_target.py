"""Shared helper for probes: trade toward fixed target weights with a 3% dead-band."""


def orders_for(targets, portfolio_state, cash):
    prices = portfolio_state["last_prices"]
    held = {p["ticker"]: p["quantity"] for p in portfolio_state["positions"]}
    equity = cash + sum(q * prices.get(t, 0.0) for t, q in held.items())
    orders = []
    for t in sorted(set(held) | set(targets)):
        px = prices.get(t)
        if not px:
            continue
        delta = int(targets.get(t, 0.0) * equity / px) - held.get(t, 0.0)
        if targets.get(t, 0.0) == 0.0 and held.get(t, 0.0) > 0:
            delta = -held[t]
        elif abs(delta) * px < 0.03 * equity:
            continue
        if delta:
            orders.append({"ticker": t, "side": "buy" if delta > 0 else "sell", "quantity": abs(delta)})
    return orders
