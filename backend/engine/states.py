"""Verification and freshness state machines.

Verification and freshness are *parallel* dimensions: a VERIFIED incident can
also become STALE. The UI shows both (Architecture 5.6).
"""
from __future__ import annotations

from .config import EngineConfig
from .domain import Category, FreshnessState, Incident, VerificationState, utcnow


def next_verification_state(
    inc: Incident,
    n_independent: int,
    confirms: int,
    denies: int,
    official_match: bool,
    cfg: EngineConfig,
) -> VerificationState:
    """Pure transition function from current signals."""
    # Terminal denial dominates: a field DENY without confirms debunks.
    if denies > 0 and confirms == 0:
        return VerificationState.DEBUNKED

    # Mixed field signals -> disputed.
    if confirms > 0 and denies > 0:
        return VerificationState.DISPUTED

    # Strong positive verification.
    if confirms > 0:
        return VerificationState.VERIFIED

    # Official corroboration + high confidence can auto-verify without a responder.
    if official_match and inc.confidence >= cfg.confidence_high and not inc.manipulation_flag:
        return VerificationState.VERIFIED

    if n_independent >= cfg.min_sources_corroborating:
        return VerificationState.CORROBORATING

    return VerificationState.UNVERIFIED


def compute_freshness(inc: Incident, cfg: EngineConfig) -> FreshnessState:
    dt_min = (utcnow() - inc.last_evidence_at).total_seconds() / 60.0
    tau = cfg.tau_min.get(inc.category, 40.0)
    if dt_min >= cfg.expire_factor * tau:
        return FreshnessState.EXPIRED
    if dt_min >= cfg.stale_factor * tau:
        return FreshnessState.STALE
    if dt_min >= cfg.aging_min:
        return FreshnessState.AGING
    if dt_min >= cfg.recent_min:
        return FreshnessState.RECENT
    return FreshnessState.FRESH


def is_publishable(inc: Incident) -> bool:
    """Only VERIFIED and not stale/expired incidents may be published."""
    return (
        inc.verification_state == VerificationState.VERIFIED
        and inc.freshness_state in (FreshnessState.FRESH, FreshnessState.RECENT, FreshnessState.AGING)
    )
