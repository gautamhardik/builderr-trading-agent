"""Probe: the 1.35x TQQQ+SOXL pair, but only while QQQ trends up; cash otherwise.

Uptrend = QQQ close above its 50-day SMA and 20-day SMA above 50-day SMA.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _target import orders_for  # noqa: E402

TARGETS = {"TQQQ": 0.225, "SOXL": 0.225}


def decide(market_state, portfolio_state, cash):
    closes = [b["close"] for b in market_state.get("QQQ", [])]
    if len(closes) < 50:
        return []
    sma20, sma50 = sum(closes[-20:]) / 20, sum(closes[-50:]) / 50
    risk_on = closes[-1] > sma50 and sma20 > sma50
    return orders_for(TARGETS if risk_on else {}, portfolio_state, cash)
