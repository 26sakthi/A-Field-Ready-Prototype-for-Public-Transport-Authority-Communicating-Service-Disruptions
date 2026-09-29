"""Explainable confidence scoring.

Formula (docs/05-Algorithm-Parameters-And-Formulas.md §4):
    confidence = 100 * clamp(w_c*corr + w_r*rep + w_v*resp + w_o*off + w_t*rec, 0, 1)

Default weights (EngineConfig):
    w_responder=0.35, w_corroboration=0.25, w_official=0.20,
    w_reputation=0.10, w_recency=0.10  (sum = 1.00)

Every component is returned in a ConfidenceBreakdown so the "why this score"
drill-down shows exactly what produced the number (Architecture NFR-3).

Error boundary: if breakdown components do not sum to total within 0.5,
the 'why this score' UI will display misleading information. The test
`test_confidence_breakdown_sums_to_total` enforces this invariant.
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
    """Diminishing-returns corroboration signal using log-scaling.

    Formula: log2(1 + n) / log2(1 + cap)
    This ensures 50 copy-paste retweets do not count the same as
    50 genuinely independent sources. The cap (default 6) means that
    additional sources beyond 6 contribute progressively less weight.

    Args:
        n_independent: Count of distinct, non-duplicate effective sources.
        cfg: Engine configuration holding corroboration_cap.

    Returns:
        Signal in [0.0, 1.0].

    Error boundary: If n_independent is inflated by uncollapsed duplicates,
    this signal is also inflated — hence text Jaccard collapsing must run
    BEFORE this function (enforced by the pipeline order in pipeline.py).
    """
    if n_independent <= 0:
        return 0.0
    cap = cfg.corroboration_cap
    return _clamp(math.log2(1 + n_independent) / math.log2(1 + cap))


def reputation_signal(reporters: list[Reporter], cfg: EngineConfig) -> float:
    """Mean reputation of the independent source reporters.

    Reputation is behaviour-based: confirmed reports raise it, debunked
    reports lower it. It is never identity-based (PRD §9 bias guard).
    New reporters receive a neutral prior (default 0.5) rather than 0,
    avoiding penalising low-connectivity communities.

    Args:
        reporters: List of Reporter objects for independent sources.
        cfg: Engine config holding new_reporter_reputation prior.

    Returns:
        Signal in [0.0, 1.0].
    """
    if not reporters:
        return cfg.new_reporter_reputation
    return _clamp(sum(r.reputation for r in reporters) / len(reporters))


def responder_signal(confirms: int, denies: int) -> float:
    """Net responder verification signal in [-1.0, 1.0].

    A single CONFIRM from a trained field responder adds the maximum
    positive value (+1.0). A single unchallenged DENY collapses this
    to -1.0, driving the incident toward DISPUTED or DEBUNKED.
    Mixed signals are netted (confirms - denies), giving a nuanced
    signal when multiple responders disagree.

    Args:
        confirms: Number of CONFIRM verification events.
        denies:   Number of DENY verification events.

    Returns:
        Signal in [-1.0, 1.0]; 0.0 if no responder has acted.

    Error boundary: responder_signal is the highest-weight component
    (w_v=0.35). A single DENY from a malicious insider can therefore
    significantly suppress a legitimate incident — mitigated by the
    DISPUTED state requiring officer review before DEBUNKED.
    """
    if confirms == 0 and denies == 0:
        return 0.0
    return _clamp(confirms - denies, -1.0, 1.0)


def official_signal(match: bool) -> float:
    return 1.0 if match else 0.0


def recency_signal(last_evidence_at, category: Category, cfg: EngineConfig) -> float:
    """Exponential decay freshness signal based on time since last evidence.

    Formula: exp(-max(0, Δt_min) / τ_category)

    τ (decay constant) is category-specific because different incident
    types have different operational lifespans:
      FLOOD: 90 min (sustained), FIRE: 60 min, SAFETY: 60 min,
      BREAKDOWN: 45 min, OTHER: 40 min, DELAY: 30 min, CROWDING: 20 min.

    Args:
        last_evidence_at: Timestamp of the most recent report or verification.
        category: Incident category determining τ.
        cfg: Engine config holding tau_min table.

    Returns:
        Signal in (0.0, 1.0]; decays asymptotically toward 0 but never
        reaches it exactly (exponential decay).
    """
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
