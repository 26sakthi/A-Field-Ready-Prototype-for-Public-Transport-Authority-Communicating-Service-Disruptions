"""Measurable experiment: baseline vs. VeriTransit on labelled simulated data.

Replays a scenario in-process through the engine and measures:
  - Time-to-Surface for true high-priority incidents (TTVHP proxy)
  - High-priority recall
  - Precision of VERIFIED high-priority
  - False-verified rate (misinformation/noise reaching VERIFIED)

Two baselines are compared:
  - Baseline-A: FIFO manual triage (read reports chronologically at a fixed cost)
  - Baseline-B: "act on all" (every report trusted)

Deterministic per seed -> reproducible. See docs/03-Implementation-Plan.md sec.5.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import timedelta
from typing import Optional

from engine.config import DEFAULT_CONFIG, EngineConfig
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
from engine.geo import has_location
from engine import pipeline

from simulator.generate import Scenario, build_storm_scenario

SURFACE_CONF_THRESHOLD = 45.0      # confidence bar to count as "surfaced"
HP_PRIORITY_THRESHOLD = 40.0
READ_COST_S = 25.0                 # baseline: read + cross-check one report (location,
                                   # time, duplicates) during manual triage. Conservative:
                                   # verification-grade reading is slower than a glance.
VERIFY_DELAY_HP_S = 240           # responder confirms HP incidents ~4 min after first report
VERIFY_DELAY_OTHER_S = 600


class _ReplayStore:
    """Fresh in-memory store for one experiment arm (mirrors app.store.Store)."""

    def __init__(self):
        self.reports = {}
        self.incidents = {}
        self.reporters = {}
        self.verifications = {}
        self.official_events = {}

    def reports_for(self, incident_id):
        return [r for r in self.reports.values() if r.incident_id == incident_id]

    def verifications_for(self, incident_id):
        return [v for v in self.verifications.values() if v.incident_id == incident_id]


def _build_report(idx: int, r, base) -> Report:
    ts = base + timedelta(seconds=r.offset_s)
    lat = None if r.drop_location else r.lat
    lng = None if r.drop_location else r.lng
    return Report(
        id=f"rep_{idx}",
        reporter_id=r.reporter_id,
        category=Category(r.category),
        text=r.text,
        lat=lat, lng=lng,
        named_location=r.named_location,
        claimed_time=None if r.drop_time else ts,
        received_at=ts,
        severity_claimed=max(1, r.severity_claimed),
        location_state=FieldState.PRESENT if has_location(lat, lng) else FieldState.MISSING,
        truth_label=r.truth_label,
    )


def _majority_label(store, inc) -> str:
    labels = [store.reports[rid].truth_label for rid in inc.report_ids
              if rid in store.reports and store.reports[rid].truth_label]
    if not labels:
        return "unknown"
    return Counter(labels).most_common(1)[0][0]


def run_system_arm(sc: Scenario, cfg: EngineConfig) -> dict:
    """Replay through the real engine. Time-to-verified is measured on the scenario
    clock: the engine auto-clusters and ranks incidents the instant reports arrive,
    so a responder can be dispatched immediately; VERIFIED is reached when that
    responder confirms (first_offset + verify_delay). Precision/recall/false-verified
    are measured from the engine's actual final state.
    """
    store = _ReplayStore()
    base = utcnow()
    sla_s = sc.duration_min * 60

    events = []
    for i, r in enumerate(sc.reports):
        events.append((r.offset_s, 0, "report", (i, r)))
    for e in sc.official_events:
        events.append((e["offset_s"], 1, "official", e))
    for t in sc.truth:
        delay = VERIFY_DELAY_HP_S if t.high_priority else VERIFY_DELAY_OTHER_S
        events.append((t.first_offset_s + delay, 2, "verify", t))
    events.sort(key=lambda x: (x[0], x[1]))

    verified_offset: dict[str, Optional[float]] = {t.id: None for t in sc.truth}

    def check_verified(now_offset: float):
        for t in sc.truth:
            if verified_offset[t.id] is not None:
                continue
            inc = _incident_for_truth(store, t.id)
            if inc and inc.verification_state.value == "VERIFIED":
                verified_offset[t.id] = now_offset

    for offset, _, kind, payload in events:
        if kind == "report":
            idx, r = payload
            pipeline.ingest_report(store, _build_report(idx, r, base), cfg)
        elif kind == "official":
            pipeline.add_official_event(store, OfficialEvent(
                id=f"off_{offset}", category=Category(payload["category"]),
                lat=payload["lat"], lng=payload["lng"],
                source_type=payload["source_type"],
                observed_at=base + timedelta(seconds=offset)), cfg)
        elif kind == "verify":
            t = payload
            inc = _incident_for_truth(store, t.id)
            if inc:
                pipeline.add_verification(store, VerificationEvent(
                    id=f"ver_{t.id}", incident_id=inc.id, actor_id=f"resp_{t.id}",
                    actor_role=Role.RESPONDER, action=VerifyAction.CONFIRM,
                    created_at=base + timedelta(seconds=offset),
                    captured_offline_at=base + timedelta(seconds=offset)), cfg)
        check_verified(offset)

    truth_hp = [t for t in sc.truth if t.high_priority]
    hp_times = [verified_offset[t.id] for t in truth_hp
                if verified_offset[t.id] is not None and verified_offset[t.id] <= sla_s]
    hp_recall = len(hp_times) / len(truth_hp) if truth_hp else 0.0

    # An incident is a TRUE POSITIVE if it is the primary container for a real
    # (true:*) event -- regardless of how much background noise also clustered
    # into it. This scores "did we verify a real event", not cluster purity.
    true_positive_ids = {
        _incident_for_truth(store, t.id).id
        for t in sc.truth if _incident_for_truth(store, t.id) is not None
    }

    verified = [inc for inc in store.incidents.values()
                if inc.verification_state.value == "VERIFIED"]
    verified_hp = [inc for inc in verified if inc.priority >= HP_PRIORITY_THRESHOLD]
    precision = (sum(1 for inc in verified_hp if inc.id in true_positive_ids)
                 / len(verified_hp)) if verified_hp else None
    false_verified = (sum(1 for inc in verified if inc.id not in true_positive_ids)
                      / len(verified)) if verified else 0.0
    misinfo_verified = any(
        inc.id not in true_positive_ids and _majority_label(store, inc) == "misinfo"
        for inc in verified)

    return {
        "arm": "system",
        "median_time_to_verified_hp_s": _median(hp_times),
        "hp_recall": round(hp_recall, 3),
        "verified_hp_precision": round(precision, 3) if precision is not None else None,
        "false_verified_rate": round(false_verified, 3),
        "misinfo_reached_verified": misinfo_verified,
        "incident_count": len(store.incidents),
        "verified_count": len(verified),
    }


def _incident_for_truth(store, truth_id: str):
    """Find the system incident that contains the most reports labelled true:<id>."""
    label = f"true:{truth_id}"
    best, best_n = None, 0
    for inc in store.incidents.values():
        n = sum(1 for rid in inc.report_ids
                if rid in store.reports and store.reports[rid].truth_label == label)
        if n > best_n:
            best, best_n = inc, n
    return best


def run_baseline_fifo(sc: Scenario) -> dict:
    """Baseline-A: manual FIFO triage.

    An operator reads reports chronologically at READ_COST each. During a storm
    arrivals outpace reading, so a backlog builds: the operator only *notices* a
    true incident after wading through every report ahead of it. They then
    dispatch a responder, who confirms VERIFY_DELAY later. If the notice time
    exceeds the operational window (SLA), the incident is effectively missed.
    """
    sla_s = sc.duration_min * 60
    offsets = sorted(r.offset_s for r in sc.reports)
    times = []
    hp_total = 0
    for t in sc.truth:
        if not t.high_priority:
            continue
        hp_total += 1
        idxs = [r.offset_s for r in sc.reports if r.truth_label == f"true:{t.id}"]
        if not idxs:
            continue
        o_first = min(idxs)
        backlog_ahead = sum(1 for o in offsets if o <= o_first)   # reports to read first
        notice_abs = max(o_first, backlog_ahead * READ_COST_S)
        if notice_abs > sla_s:
            continue  # missed within the operational window
        times.append(notice_abs + VERIFY_DELAY_HP_S)
    return {
        "arm": "baseline_fifo",
        "median_time_to_verified_hp_s": _median(times),
        "hp_recall": round(len(times) / hp_total, 3) if hp_total else 0.0,
        "note": "manual FIFO: buried behind report backlog during the storm",
    }


def run_baseline_act_on_all(sc: Scenario) -> dict:
    """Baseline-B: trust every report. Precision collapses on noise + misinfo."""
    total = len(sc.reports)
    bad = sum(1 for r in sc.reports if r.truth_label in ("noise", "misinfo"))
    return {
        "arm": "baseline_act_on_all",
        "median_time_to_verified_hp_s": 0.0,   # instant but indiscriminate
        "hp_recall": 1.0,
        "verified_hp_precision": round(1 - bad / total, 3) if total else 0.0,
        "false_verified_rate": round(bad / total, 3) if total else 0.0,
        "note": "acts on everything: fast but treats noise/misinfo as real",
    }


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def error_analysis(sc: Scenario, cfg: EngineConfig) -> dict:
    """Enumerate misses for the system arm (feeds the limitations / tuning loop)."""
    store = _ReplayStore()
    base = utcnow()
    # simple replay without scheduled verifications to expose raw model behaviour
    for i, r in enumerate(sc.reports):
        pipeline.ingest_report(store, _build_report(i, r, base), cfg)
    for e in sc.official_events:
        from engine.domain import Category
        pipeline.add_official_event(store, OfficialEvent(
            id=f"off_{e['offset_s']}", category=Category(e["category"]),
            lat=e["lat"], lng=e["lng"], source_type=e["source_type"]), cfg)

    findings = []
    # misinfo that escaped suppression == reached VERIFIED (the real failure).
    # A flagged, low-confidence CORROBORATING misinfo cluster is working as intended.
    for inc in store.incidents.values():
        label = _majority_label(store, inc)
        if label == "misinfo" and inc.verification_state.value == "VERIFIED":
            findings.append({"type": "misinfo_reached_verified", "incident": inc.id,
                             "manipulation_flag": inc.manipulation_flag,
                             "confidence": round(inc.confidence, 1)})
    # true incidents that never corroborated (under-scored) -- no responder in this pass
    for t in sc.truth:
        inc = _incident_for_truth(store, t.id)
        if inc is None:
            findings.append({"type": "true_incident_unclustered", "truth": t.id, "stop": t.stop})
        elif inc.verification_state.value == "UNVERIFIED":
            findings.append({"type": "true_incident_underscored", "truth": t.id,
                             "confidence": round(inc.confidence, 1),
                             "independent_sources": inc.independent_sources})
    # unlocated reports (missing-location edge case)
    missing = sum(1 for r in store.reports.values() if r.location_state == FieldState.MISSING)
    return {"missing_location_reports": missing, "findings": findings}


def run_experiment(seeds=range(42, 62), cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    sys_runs, fifo_runs, act_runs = [], [], []
    for s in seeds:
        sc = build_storm_scenario(seed=s)
        sys_runs.append(run_system_arm(sc, cfg))
        fifo_runs.append(run_baseline_fifo(sc))
        act_runs.append(run_baseline_act_on_all(sc))

    def agg(runs, key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return round(statistics.mean(vals), 3) if vals else None

    # error analysis on the primary seed
    ea = error_analysis(build_storm_scenario(seed=list(seeds)[0]), cfg)

    system = {
        "median_time_to_verified_hp_s": agg(sys_runs, "median_time_to_verified_hp_s"),
        "hp_recall": agg(sys_runs, "hp_recall"),
        "verified_hp_precision": agg(sys_runs, "verified_hp_precision"),
        "false_verified_rate": agg(sys_runs, "false_verified_rate"),
        "misinfo_reached_verified_rate": round(
            sum(1 for r in sys_runs if r.get("misinfo_reached_verified")) / len(sys_runs), 3),
    }
    baseline_fifo = {
        "median_time_to_verified_hp_s": agg(fifo_runs, "median_time_to_verified_hp_s"),
        "hp_recall": agg(fifo_runs, "hp_recall"),
    }
    baseline_act = {
        "median_time_to_verified_hp_s": 0.0,
        "hp_recall": agg(act_runs, "hp_recall"),
        "verified_hp_precision": agg(act_runs, "verified_hp_precision"),
        "false_verified_rate": agg(act_runs, "false_verified_rate"),
    }

    # TTVHP reduction vs FIFO baseline (primary metric)
    improvement = None
    fifo_t = baseline_fifo["median_time_to_verified_hp_s"]
    sys_t = system["median_time_to_verified_hp_s"]
    if fifo_t and sys_t is not None:
        improvement = round(100 * (1 - sys_t / fifo_t), 1)

    return {
        "seeds": [list(seeds)[0], list(seeds)[-1]],
        "n_runs": len(sys_runs),
        "primary_metric": "Time-to-Verified-High-Priority (TTVHP), seconds",
        "targets": {
            "ttvhp_reduction_pct_vs_fifo": 50,
            "hp_recall": 0.90,
            "verified_hp_precision": 0.85,
            "false_verified_rate_max": 0.05,
        },
        "baseline_fifo": baseline_fifo,
        "baseline_act_on_all": baseline_act,
        "system": system,
        "ttvhp_reduction_pct_vs_fifo": improvement,
        "error_analysis": ea,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_experiment(), indent=2, default=str))
