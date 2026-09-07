"""Orchestration pipeline: ingest -> cluster -> score -> state.

Operates over a duck-typed Store that exposes the collections it needs. The
pipeline is pure with respect to time (uses utcnow) and otherwise deterministic,
so experiments replay identically for a given seed.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from . import cluster, confidence, independence, priority, states
from .config import EngineConfig
from .domain import (
    Category,
    Incident,
    OfficialEvent,
    Report,
    Reporter,
    VerificationEvent,
    VerifyAction,
    utcnow,
)


class Store(Protocol):
    reports: dict[str, Report]
    incidents: dict[str, Incident]
    reporters: dict[str, Reporter]
    verifications: dict[str, VerificationEvent]
    official_events: dict[str, OfficialEvent]

    def reports_for(self, incident_id: str) -> list[Report]: ...
    def verifications_for(self, incident_id: str) -> list[VerificationEvent]: ...


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def ensure_reporter(store: Store, reporter_id: str, channel: str, cfg: EngineConfig) -> Reporter:
    rep = store.reporters.get(reporter_id)
    if rep is None:
        rep = Reporter(id=reporter_id, channel=channel, reputation=cfg.new_reporter_reputation)
        store.reporters[reporter_id] = rep
    return rep


def ingest_report(store: Store, report: Report, cfg: EngineConfig) -> Incident:
    """Add a report, (re)cluster, and recompute its incident."""
    ensure_reporter(store, report.reporter_id, "app", cfg)
    store.reports[report.id] = report

    inc = cluster.find_incident_for(report, store.incidents.values(), cfg)
    if inc is None:
        inc = Incident(
            id=_new_id("inc"),
            category=report.category,
            center_lat=report.lat,
            center_lng=report.lng,
            severity=report.severity_claimed,
            first_reported_at=report.claimed_time or report.received_at,
        )
        store.incidents[inc.id] = inc

    report.incident_id = inc.id
    if report.id not in inc.report_ids:
        inc.report_ids.append(report.id)

    recompute_incident(store, inc, cfg)
    return inc


def add_verification(store: Store, ev: VerificationEvent, cfg: EngineConfig) -> Incident:
    store.verifications[ev.id] = ev
    inc = store.incidents[ev.incident_id]
    recompute_incident(store, inc, cfg)
    _apply_reputation(store, inc, ev, cfg)
    return inc


def add_official_event(store: Store, ev: OfficialEvent, cfg: EngineConfig) -> None:
    store.official_events[ev.id] = ev
    # re-score incidents that could now match
    for inc in store.incidents.values():
        recompute_incident(store, inc, cfg)


def recompute_incident(store: Store, inc: Incident, cfg: EngineConfig) -> None:
    reports = store.reports_for(inc.id)
    verifs = store.verifications_for(inc.id)

    cluster.update_center(inc, reports)

    # evidence recency = most recent report or verification (by capture time)
    evidence_times = [r.claimed_time or r.received_at for r in reports]
    evidence_times += [v.captured_offline_at or v.created_at for v in verifs]
    if evidence_times:
        inc.last_evidence_at = max(evidence_times)

    n_ind = independence.independent_sources(reports, cfg)
    inc.independent_sources = n_ind
    inc.manipulation_flag = independence.detect_burst(reports, cfg)

    reporters = [store.reporters[r.reporter_id] for r in reports if r.reporter_id in store.reporters]

    inc.confirms = sum(1 for v in verifs if v.action == VerifyAction.CONFIRM)
    inc.denies = sum(1 for v in verifs if v.action == VerifyAction.DENY)

    inc.official_match = confidence.official_match(
        inc.center_lat, inc.center_lng, inc.category,
        list(store.official_events.values()), cfg,
    )

    bd = confidence.compute_confidence(
        n_independent=n_ind,
        reporters=reporters,
        confirms=inc.confirms,
        denies=inc.denies,
        match=inc.official_match,
        last_evidence_at=inc.last_evidence_at,
        category=inc.category,
        manipulation=inc.manipulation_flag,
        cfg=cfg,
    )
    inc.breakdown = bd
    inc.confidence = bd.total

    # severity = max claimed across reports (worst case)
    if reports:
        inc.severity = max(r.severity_claimed for r in reports)

    inc.verification_state = states.next_verification_state(
        inc, n_ind, inc.confirms, inc.denies, inc.official_match, cfg
    )
    inc.freshness_state = states.compute_freshness(inc, cfg)
    inc.priority = priority.compute_priority(inc.severity, inc.confidence, inc.category, cfg)
    inc.publishable = states.is_publishable(inc)


def refresh_freshness(store: Store, cfg: EngineConfig) -> list[str]:
    """Advance freshness for all incidents (called on a timer). Returns changed ids."""
    changed = []
    for inc in store.incidents.values():
        new_state = states.compute_freshness(inc, cfg)
        if new_state != inc.freshness_state:
            inc.freshness_state = new_state
            inc.publishable = states.is_publishable(inc)
            changed.append(inc.id)
    return changed


def _apply_reputation(store: Store, inc: Incident, ev: VerificationEvent, cfg: EngineConfig) -> None:
    """A responder verification nudges the reputation of contributing reporters."""
    reports = store.reports_for(inc.id)
    for r in reports:
        rep = store.reporters.get(r.reporter_id)
        if not rep:
            continue
        if ev.action == VerifyAction.CONFIRM:
            rep.confirmed_count += 1
            rep.reputation = min(1.0, rep.reputation + 0.05)
        elif ev.action == VerifyAction.DENY:
            rep.debunked_count += 1
            rep.reputation = max(0.0, rep.reputation - 0.1)
