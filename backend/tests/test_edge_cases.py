"""The five required edge / failure cases (PRD sec.8)."""
from __future__ import annotations

from datetime import timedelta

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
from engine import pipeline

CFG = EngineConfig()


class Store:
    def __init__(self):
        self.reports, self.incidents, self.reporters = {}, {}, {}
        self.verifications, self.official_events = {}, {}

    def reports_for(self, iid):
        return [r for r in self.reports.values() if r.incident_id == iid]

    def verifications_for(self, iid):
        return [v for v in self.verifications.values() if v.incident_id == iid]


def mk(rid, reporter, text, cat=Category.FLOOD, lat=13.08, lng=80.27, sev=4, t=None):
    return Report(id=rid, reporter_id=reporter, category=cat, lat=lat, lng=lng,
                  text=text, severity_claimed=sev, claimed_time=t or utcnow(),
                  received_at=t or utcnow())


# --- Edge case 1: conflicting corroboration -> DISPUTED --------------------

def test_conflicting_reports_go_disputed():
    s = Store()
    pipeline.ingest_report(s, mk("r1", "a", "flood at central"), CFG)
    inc = pipeline.ingest_report(s, mk("r2", "b", "central platform flooded"), CFG)
    pipeline.add_verification(s, VerificationEvent(
        id="v1", incident_id=inc.id, actor_id="resp1", actor_role=Role.RESPONDER,
        action=VerifyAction.CONFIRM), CFG)
    inc = pipeline.add_verification(s, VerificationEvent(
        id="v2", incident_id=inc.id, actor_id="resp2", actor_role=Role.RESPONDER,
        action=VerifyAction.DENY), CFG)
    assert inc.verification_state.value == "DISPUTED"


# --- Edge case 2: stale / expired freshness --------------------------------

def test_stale_then_expired_over_time():
    s = Store()
    old = utcnow() - timedelta(minutes=200)  # well past flood tau*expire_factor
    inc = pipeline.ingest_report(s, mk("r1", "a", "flood", t=old), CFG)
    pipeline.ingest_report(s, mk("r2", "b", "flooded here", t=old), CFG)
    pipeline.refresh_freshness(s, CFG)
    assert inc.freshness_state.value in ("STALE", "EXPIRED")
    # a stale incident is not publishable
    assert inc.publishable is False


# --- Edge case 3: coordinated misinformation burst -------------------------

def test_misinformation_burst_flagged_and_not_verified():
    s = Store()
    now = utcnow()
    inc = None
    for i in range(12):  # many posts, only 2 reporters, identical text, ~seconds apart
        inc = pipeline.ingest_report(s, mk(
            f"r{i}", f"bot_{i % 2}", "EVACUATE NOW everyone danger",
            cat=Category.SAFETY, t=now + timedelta(seconds=i * 4)), CFG)
    assert inc.manipulation_flag is True
    assert inc.verification_state.value != "VERIFIED"
    assert inc.confidence < 50  # corroboration credit collapsed


# --- Edge case 4: missing location / time ----------------------------------

def test_missing_location_not_clustered_but_retained():
    s = Store()
    r = Report(id="r1", reporter_id="a", category=Category.FLOOD, lat=None, lng=None,
               text="flood somewhere", location_state=FieldState.MISSING)
    inc = pipeline.ingest_report(s, r, CFG)
    assert r.location_state == FieldState.MISSING
    assert r.id in s.reports                      # retained, never dropped
    assert inc.center_lat is None                 # not placed at (0,0)


# --- Edge case 5: connectivity loss / late sync ----------------------------

def test_delayed_sync_uses_capture_time_not_receipt_time():
    # A responder captures reports AND a verification offline, 20 min ago, then
    # syncs now. Scoring must use capture time (20 min ago), not sync time (now).
    s = Store()
    captured = utcnow() - timedelta(minutes=20)
    pipeline.ingest_report(s, mk("r1", "a", "flood one", t=captured), CFG)
    inc = pipeline.ingest_report(s, mk("r2", "b", "flood two", t=captured), CFG)
    ev = VerificationEvent(
        id="v1", incident_id=inc.id, actor_id="resp", actor_role=Role.RESPONDER,
        action=VerifyAction.CONFIRM, created_at=utcnow(), captured_offline_at=captured)
    inc = pipeline.add_verification(s, ev, CFG)
    assert inc.verification_state.value == "VERIFIED"
    # evidence recency is anchored to capture time (~20 min ago), not sync time (now)
    assert (utcnow() - inc.last_evidence_at).total_seconds() >= 19 * 60
