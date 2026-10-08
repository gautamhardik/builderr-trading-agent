"""Probe: always hold 22.5% TQQQ + 22.5% SOXL (1.35x beta gross, headroom for drift).

The realistic ceiling on variance under the 30%-per-name and 1.5x-beta rules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _target import orders_for  # noqa: E402

TARGETS = {"TQQQ": 0.225, "SOXL": 0.225}


def decide(market_state, portfolio_state, cash):
    return orders_for(TARGETS, portfolio_state, cash)
