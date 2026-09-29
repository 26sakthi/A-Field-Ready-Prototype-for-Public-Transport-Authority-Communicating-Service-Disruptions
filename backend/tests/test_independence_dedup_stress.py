"""Comprehensive stress tests for independence, deduplication, and synthetic edge cases.

Edge cases incorporated:
1. Coordinated burst spam attack (high volume, few reporters, copy-paste text, short time span).
2. Duplicate coordinates across split timestamps (verifying temporal window anchoring).
3. Multi-account paraphrased text spam (testing token Jaccard similarity thresholds).
4. Cross-category conflicting report burst at identical coordinates.
5. Missing location high-volume burst (verifying centroid isolation).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.config import EngineConfig
from engine.domain import (
    Category,
    FieldState,
    Incident,
    OfficialEvent,
    Report,
    Role,
    VerificationEvent,
    VerifyAction,
    utcnow,
)
from engine import cluster, confidence, independence, pipeline, priority

CFG = EngineConfig()


class MemoryStore:
    def __init__(self):
        self.reports: dict[str, Report] = {}
        self.incidents: dict[str, Incident] = {}
        self.reporters: dict[str, any] = {}
        self.verifications: dict[str, VerificationEvent] = {}
        self.official_events: dict[str, OfficialEvent] = {}

    def reports_for(self, iid: str) -> list[Report]:
        return [r for r in self.reports.values() if r.incident_id == iid]

    def verifications_for(self, iid: str) -> list[VerificationEvent]:
        return [v for v in self.verifications.values() if v.incident_id == iid]


def make_report(
    rid: str,
    reporter_id: str,
    text: str = "water on track near platform 1",
    cat: Category = Category.FLOOD,
    lat: float | None = 13.0827,
    lng: float | None = 80.2707,
    sev: int = 4,
    dt: datetime | None = None,
    loc_state: FieldState = FieldState.PRESENT,
) -> Report:
    t = dt or utcnow()
    return Report(
        id=rid,
        reporter_id=reporter_id,
        category=cat,
        lat=lat,
        lng=lng,
        text=text,
        severity_claimed=sev,
        claimed_time=t,
        received_at=t,
        location_state=loc_state if lat is not None else FieldState.MISSING,
    )


# --- Edge Case 1: Coordinated Burst Spam Attack ---

def test_burst_coordinated_spam_collapses_and_flags_manipulation():
    """Stress test: 25 spam reports from 2 bot accounts with identical copy-paste text within 45 seconds."""
    s = MemoryStore()
    base_time = utcnow()
    spam_text = "EMERGENCY BREAKING NEWS EVACUATE CENTRAL STATION IMMEDIATELY FLOODING CRITICAL"

    # Ingest 25 spam reports from 2 bot IDs
    inc = None
    for i in range(25):
        bot_id = f"bot_account_{i % 2}"
        r = make_report(
            rid=f"spam_{i}",
            reporter_id=bot_id,
            text=spam_text,
            cat=Category.SAFETY,
            lat=13.0827,
            lng=80.2707,
            dt=base_time + timedelta(seconds=i * 1.8),
        )
        inc = pipeline.ingest_report(s, r, CFG)

    # Ingest 2 genuine, distinct reports from real users in the same area
    r_real1 = make_report("real_1", "user_alpha", "water leaking near track 3", cat=Category.SAFETY, dt=base_time + timedelta(seconds=10))
    r_real2 = make_report("real_2", "user_beta", "flooding observed at central platform", cat=Category.SAFETY, dt=base_time + timedelta(seconds=20))
    inc = pipeline.ingest_report(s, r_real1, CFG)
    inc = pipeline.ingest_report(s, r_real2, CFG)

    reports = s.reports_for(inc.id)

    # 1. Burst detection must trigger
    assert independence.detect_burst(reports, CFG) is True
    assert inc.manipulation_flag is True

    # 2. Independent source calculation must collapse the 25 spam reports to 1 effective source,
    # plus the 2 distinct genuine reports => total 3 independent sources.
    effective_sources = independence.independent_sources(reports, CFG)
    assert effective_sources == 3

    # 3. Confidence score must reflect the 0.20 manipulation penalty on corroboration credit
    # and stay below auto-verification bar (70.0)
    assert inc.confidence < 60.0
    assert inc.verification_state.value != "VERIFIED"


# --- Edge Case 2: Duplicate Coordinates Across Split Timestamps ---

def test_duplicate_coords_across_split_timestamps_seed_separate_incidents():
    """Stress test: Reports submitted at identical GPS coordinates (13.0827, 80.2707) across split time windows.

    Reports at t_0 and t_0 + 5m must merge into Incident #1.
    Reports at t_0 + 35m (> 15m window from onset) must seed Incident #2.
    Reports at t_0 + 120m (> 15m window from onset) must seed Incident #3.
    """
    s = MemoryStore()
    t0 = utcnow() - timedelta(hours=3)

    # Phase 1: t0 and t0 + 5min (should cluster into incident 1)
    r1 = make_report("r1", "rep_a", "flooding at junction", dt=t0)
    r2 = make_report("r2", "rep_b", "water on track junction", dt=t0 + timedelta(minutes=5))
    inc1 = pipeline.ingest_report(s, r1, CFG)
    inc1_b = pipeline.ingest_report(s, r2, CFG)

    assert inc1.id == inc1_b.id
    assert len(s.incidents) == 1

    # Phase 2: t0 + 35min (> 15min temporal window T from onset t0)
    r3 = make_report("r3", "rep_c", "water levels high again junction", dt=t0 + timedelta(minutes=35))
    inc2 = pipeline.ingest_report(s, r3, CFG)

    assert inc2.id != inc1.id
    assert len(s.incidents) == 2

    # Phase 3: t0 + 120min (> 15min temporal window T from onset t0 + 35m)
    r4 = make_report("r4", "rep_d", "new flood accumulation junction", dt=t0 + timedelta(minutes=120))
    inc3 = pipeline.ingest_report(s, r4, CFG)

    assert inc3.id not in (inc1.id, inc2.id)
    assert len(s.incidents) == 3


# --- Edge Case 3: Multi-Account Paraphrased Spam Attack ---

def test_paraphrased_spam_jaccard_deduplication():
    """Stress test: 12 reports from 12 distinct fake reporter IDs using slight word permutations.

    Identical core token set -> Jaccard >= 0.90 -> collapses to 1 independent source.
    """
    s = MemoryStore()
    base_time = utcnow()

    # Variations with Jaccard similarity >= 0.90 (sharing core token set)
    phrases = [
        "severe flood on central platform line 1 immediately evacuate",
        "severe flood on central platform line 1 immediately evacuate now",
        "severe flood on central platform line 1 immediately evacuate station",
        "severe flood on central platform line 1 immediately evacuate area",
        "severe flood on central platform line 1 immediately evacuate people",
    ]

    inc = None
    for i, phrase in enumerate(phrases):
        r = make_report(f"para_{i}", f"fake_user_{i}", text=phrase, dt=base_time + timedelta(seconds=i * 2))
        inc = pipeline.ingest_report(s, r, CFG)

    reports = s.reports_for(inc.id)
    effective_sources = independence.independent_sources(reports, CFG)

    # High token overlap must collapse these paraphrased reports down to 1 source
    assert effective_sources == 1


# --- Edge Case 4: Cross-Category Conflicting Report Burst ---

def test_cross_category_conflicting_reports_isolate_into_separate_clusters():
    """Stress test: Simultaneous reports at identical coordinates but incompatible categories (FLOOD vs FIRE vs CROWDING)."""
    s = MemoryStore()
    now = utcnow()
    lat, lng = 13.0827, 80.2707

    r_flood = make_report("f1", "user_1", "submerged tracks", cat=Category.FLOOD, lat=lat, lng=lng, dt=now)
    r_fire = make_report("f2", "user_2", "smoke rising near transformer", cat=Category.FIRE, lat=lat, lng=lng, dt=now)
    r_crowd = make_report("c1", "user_3", "massive crowd surge at exit", cat=Category.CROWDING, lat=lat, lng=lng, dt=now)

    inc_flood = pipeline.ingest_report(s, r_flood, CFG)
    inc_fire = pipeline.ingest_report(s, r_fire, CFG)
    inc_crowd = pipeline.ingest_report(s, r_crowd, CFG)

    # Incompatible categories must seed 3 distinct incidents despite identical location and timestamp
    assert len({inc_flood.id, inc_fire.id, inc_crowd.id}) == 3
    assert len(s.incidents) == 3


# --- Edge Case 5: Missing Location High-Volume Burst ---

def test_missing_location_high_volume_burst_isolation():
    """Stress test: 15 reports with MISSING location arriving in rapid succession.

    Reports must attach to unlocated evidence list without altering spatial centroids or placing at (0,0).
    """
    s = MemoryStore()
    now = utcnow()

    inc = None
    for i in range(15):
        r = Report(
            id=f"nobg_{i}",
            reporter_id=f"anon_{i}",
            category=Category.FLOOD,
            lat=None,
            lng=None,
            text=f"flooding reported somewhere on main line batch {i}",
            severity_claimed=3,
            claimed_time=now + timedelta(seconds=i),
            received_at=now + timedelta(seconds=i),
            location_state=FieldState.MISSING,
        )
        inc = pipeline.ingest_report(s, r, CFG)

    # Missing location reports must not seed spatial lat/lng centroids
    assert inc.center_lat is None
    assert inc.center_lng is None
    assert len(s.reports) == 15
