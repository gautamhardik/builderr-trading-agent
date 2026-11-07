"""Apex All-Weather v3 candidate."""
from __future__ import annotations

import agent

POOL = agent.POOL
DEFENSIVE_POOL = agent.DEFENSIVE_POOL
BETA_3X = agent.BETA_3X
BETA_2X = agent.BETA_2X
TOP_K = agent.TOP_K
KEEP_RANK = agent.KEEP_RANK
LEADER_WEIGHT = agent.LEADER_WEIGHT
QUALITY_WEIGHT = agent.QUALITY_WEIGHT
STRONG_SLEEVE_WEIGHT = agent.STRONG_SLEEVE_WEIGHT
CONSTRUCTIVE_SLEEVE_WEIGHT = agent.CONSTRUCTIVE_SLEEVE_WEIGHT
DEFENSIVE_WEIGHT = agent.DEFENSIVE_WEIGHT
NAME_CAP = agent.NAME_CAP
DRIFT_CAP = agent.DRIFT_CAP
GROSS_LIMIT = agent.GROSS_LIMIT
BAND = agent.BAND
STOP_LOSS_PCT = agent.STOP_LOSS_PCT
MIN_BARS = agent.MIN_BARS

_beta = agent._beta
_closes = agent._closes
_sma = agent._sma
_vol = agent._vol
defensive_picks = agent.defensive_picks
regime = agent.regime
leaders = agent.leaders
targets = agent.targets
decide = agent.decide
_decide = agent._decide
