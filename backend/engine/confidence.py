"""Explainable confidence scoring.

confidence = 100 * clamp( w_c*corr + w_r*rep + w_v*resp + w_o*off + w_t*rec )

Every component is returned in a ConfidenceBreakdown so the "why this score"
drill-down shows exactly what produced the number (Architecture NFR-3).
"""
from __future__ import annotations

import math

from .config import EngineConfig
from .domain import (
    Category,
    ConfidenceBreakdown,
    OfficialEvent,
    Report,
    Reporter,
    VerificationEvent,
    VerifyAction,
    utcnow,
)
from .geo import haversine_m


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def corroboration_signal(n_independent: int, cfg: EngineConfig) -> float:
    """Diminishing-returns on independent sources."""
    if n_independent <= 0:
        return 0.0
    cap = cfg.corroboration_cap
    return _clamp(math.log2(1 + n_independent) / math.log2(1 + cap))


def reputation_signal(reporters: list[Reporter], cfg: EngineConfig) -> float:
    if not reporters:
        return cfg.new_reporter_reputation
    return _clamp(sum(r.reputation for r in reporters) / len(reporters))


def responder_signal(confirms: int, denies: int) -> float:
    """+1 for net confirmation, negative for net denial. Range [-1, 1]."""
    if confirms == 0 and denies == 0:
        return 0.0
    return _clamp(confirms - denies, -1.0, 1.0)


def official_signal(match: bool) -> float:
    return 1.0 if match else 0.0


def recency_signal(last_evidence_at, category: Category, cfg: EngineConfig) -> float:
    tau = cfg.tau_min.get(category, 40.0)
    dt_min = (utcnow() - last_evidence_at).total_seconds() / 60.0
    return _clamp(math.exp(-max(0.0, dt_min) / tau))


def official_match(
    center_lat, center_lng, category: Category,
    events: list[OfficialEvent], cfg: EngineConfig,
) -> bool:
    if center_lat is None:
        return False
    for ev in events:
        if ev.category != category and category not in (Category.SAFETY,):
            # allow safety to match any official event nearby
            if ev.category != category:
                continue
        d = haversine_m(center_lat, center_lng, ev.lat, ev.lng)
        if d <= cfg.radius_m * 1.5:
            return True
    return False


def compute_confidence(
    n_independent: int,
    reporters: list[Reporter],
    confirms: int,
    denies: int,
    match: bool,
    last_evidence_at,
    category: Category,
    manipulation: bool,
    cfg: EngineConfig,
) -> ConfidenceBreakdown:
    corr = corroboration_signal(n_independent, cfg)
    if manipulation:
        # collapse corroboration credit for coordinated bursts
        corr *= 0.2
    rep = reputation_signal(reporters, cfg)
    resp = responder_signal(confirms, denies)
    off = official_signal(match)
    rec = recency_signal(last_evidence_at, category, cfg)

    c_corr = cfg.w_corroboration * corr
    c_rep = cfg.w_reputation * rep
    c_resp = cfg.w_responder * resp
    c_off = cfg.w_official * off
    c_rec = cfg.w_recency * rec

    total = _clamp(c_corr + c_rep + c_resp + c_off + c_rec) * 100.0

    return ConfidenceBreakdown(
        corroboration=c_corr * 100.0,
        reputation=c_rep * 100.0,
        responder=c_resp * 100.0,
        official=c_off * 100.0,
        recency=c_rec * 100.0,
        total=total,
    )
