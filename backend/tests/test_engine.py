"""Unit tests for the verification engine core."""
from __future__ import annotations

from datetime import timedelta

import pytest

from engine.config import EngineConfig
from engine.domain import (
    Category,
    FieldState,
    OfficialEvent,
    Report,
    Role,
    VerificationEvent,
    VerifyAction,
    utcnow,
)
from engine import confidence, independence, pipeline, priority
from engine.cluster import find_incident_for


class Store:
    def __init__(self):
        self.reports, self.incidents, self.reporters = {}, {}, {}
        self.verifications, self.official_events = {}, {}

    def reports_for(self, iid):
        return [r for r in self.reports.values() if r.incident_id == iid]

    def verifications_for(self, iid):
        return [v for v in self.verifications.values() if v.incident_id == iid]


CFG = EngineConfig()


def mk_report(rid, reporter, cat=Category.FLOOD, lat=13.08, lng=80.27, text="water on tracks", sev=4, t=None):
    return Report(id=rid, reporter_id=reporter, category=cat, lat=lat, lng=lng,
                  text=text, severity_claimed=sev, claimed_time=t or utcnow(),
                  received_at=t or utcnow())


def test_two_independent_reports_corroborate():
    s = Store()
    pipeline.ingest_report(s, mk_report("r1", "a", text="flood at central platform"), CFG)
    inc = pipeline.ingest_report(s, mk_report("r2", "b", text="platform flooded central"), CFG)
    assert inc.independent_sources == 2
    assert inc.verification_state.value == "CORROBORATING"


def test_same_reporter_does_not_corroborate():
    s = Store()
    pipeline.ingest_report(s, mk_report("r1", "a"), CFG)
    inc = pipeline.ingest_report(s, mk_report("r2", "a"), CFG)  # same reporter
    assert inc.independent_sources == 1
    assert inc.verification_state.value == "UNVERIFIED"


def test_duplicate_text_collapses_to_one_source():
    s = Store()
    identical = "evacuate now everyone"
    pipeline.ingest_report(s, mk_report("r1", "a", text=identical), CFG)
    inc = pipeline.ingest_report(s, mk_report("r2", "b", text=identical), CFG)
    assert inc.independent_sources == 1  # near-duplicate collapsed


def test_responder_confirm_verifies():
    s = Store()
    pipeline.ingest_report(s, mk_report("r1", "a", text="flood one"), CFG)
    inc = pipeline.ingest_report(s, mk_report("r2", "b", text="flood two"), CFG)
    ev = VerificationEvent(id="v1", incident_id=inc.id, actor_id="resp",
                           actor_role=Role.RESPONDER, action=VerifyAction.CONFIRM)
    inc = pipeline.add_verification(s, ev, CFG)
    assert inc.verification_state.value == "VERIFIED"
    assert inc.confidence > 45


def test_confidence_breakdown_sums_to_total():
    s = Store()
    pipeline.ingest_report(s, mk_report("r1", "a", text="flood one"), CFG)
    inc = pipeline.ingest_report(s, mk_report("r2", "b", text="flood two"), CFG)
    bd = inc.breakdown
    parts = bd.corroboration + bd.reputation + bd.responder + bd.official + bd.recency
    assert abs(parts - bd.total) < 0.5  # breakdown explains the score


def test_priority_orders_high_severity_confident_first():
    p_hi = priority.compute_priority(5, 90.0, Category.FLOOD, CFG)
    p_lo = priority.compute_priority(2, 40.0, Category.DELAY, CFG)
    assert p_hi > p_lo


def test_new_incident_when_far_away():
    s = Store()
    pipeline.ingest_report(s, mk_report("r1", "a", lat=13.08, lng=80.27), CFG)
    pipeline.ingest_report(s, mk_report("r2", "b", lat=13.20, lng=80.40), CFG)  # ~20km
    assert len(s.incidents) == 2
