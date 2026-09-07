"""Tunable engine configuration: weights, thresholds, decay constants.

All knobs live here so the measurable experiment can sweep them and the
Metrics & Admin view can display / tune them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .domain import Category


@dataclass
class EngineConfig:
    # --- clustering ---
    radius_m: float = 250.0          # spatial window R
    time_window_min: float = 15.0    # temporal window T

    # --- confidence weights (sum ~1.0) ---
    w_corroboration: float = 0.25
    w_reputation: float = 0.10
    w_responder: float = 0.35
    w_official: float = 0.20
    w_recency: float = 0.10

    corroboration_cap: int = 6       # diminishing-returns cap on independent sources
    new_reporter_reputation: float = 0.5

    # --- recency decay tau (minutes) per category ---
    tau_min: dict = field(default_factory=lambda: {
        Category.FLOOD: 90.0,
        Category.FIRE: 60.0,
        Category.BREAKDOWN: 45.0,
        Category.SAFETY: 60.0,
        Category.CROWDING: 20.0,
        Category.DELAY: 30.0,
        Category.OTHER: 40.0,
    })

    # --- freshness thresholds (minutes) ---
    fresh_min: float = 5.0
    recent_min: float = 15.0
    aging_min: float = 45.0
    # staleness / expiry are relative to category tau
    stale_factor: float = 1.5        # STALE after stale_factor * tau
    expire_factor: float = 3.0       # EXPIRED after expire_factor * tau

    # --- state transition thresholds ---
    confidence_high: float = 70.0    # official-match auto-verify bar
    min_sources_corroborating: int = 2

    # --- anti-manipulation ---
    burst_count: int = 8             # reports...
    burst_window_min: float = 2.0    # ...within this window...
    burst_distinct_reporters: int = 3  # ...from <= this many reporters => burst
    dup_jaccard: float = 0.9

    # --- priority impact: per-category criticality 0..1 ---
    criticality: dict = field(default_factory=lambda: {
        Category.FLOOD: 1.0,
        Category.FIRE: 1.0,
        Category.SAFETY: 0.95,
        Category.BREAKDOWN: 0.7,
        Category.CROWDING: 0.75,
        Category.DELAY: 0.5,
        Category.OTHER: 0.4,
    })


DEFAULT_CONFIG = EngineConfig()
