"""Tuned Apex Sprint v2 with leverage clamp and 28.5% concentration cap."""
from __future__ import annotations

import agent

POOL = agent.POOL
BETA_3X = agent.BETA_3X
BETA_2X = agent.BETA_2X
TOP_K = agent.TOP_K
KEEP_RANK = agent.KEEP_RANK
LEADER_WEIGHT = agent.LEADER_WEIGHT
STRONG_SLEEVE_WEIGHT = agent.STRONG_SLEEVE_WEIGHT
SNAPBACK_SLEEVE_WEIGHT = agent.SNAPBACK_SLEEVE_WEIGHT
DEFENSIVE_WEIGHT = agent.DEFENSIVE_WEIGHT
NAME_CAP = agent.NAME_CAP
DRIFT_CAP = agent.DRIFT_CAP
GROSS_LIMIT = agent.GROSS_LIMIT
BAND = agent.BAND
MIN_BARS = agent.MIN_BARS

_beta = agent._beta
_closes = agent._closes
_sma = agent._sma
_vol = agent._vol
_rsi5 = agent._rsi5
defensive_picks = agent.defensive_picks
regime = agent.regime
leaders = agent.leaders
targets = agent.targets
decide = agent.decide
_decide = agent._decide
