"""VeriTransit API: ingestion, verification, dashboard queries, offline sync, metrics.

Human-in-the-loop: the engine ranks and scores; officers/responders verify;
PIO/decision-maker publish. Every mutation is audited.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from engine import pipeline
from engine.config import DEFAULT_CONFIG
from engine.domain import (
    Category,
    FieldState,
    OfficialEvent,
    Report,
    Role,
    SyncState,
    VerificationEvent,
    VerifyAction,
    utcnow,
)
from engine.geo import has_location
from engine.states import is_publishable

from .schemas import (
    OfficialIn,
    PublishIn,
    ReportIn,
    SyncIn,
    VerifyIn,
    incident_detail,
    incident_summary,
    report_out,
    verification_out,
)
from .store import STORE
from .ws import manager

CFG = DEFAULT_CONFIG

app = FastAPI(title="VeriTransit API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _cat(value: str) -> Category:
    try:
        return Category(value)
    except ValueError:
        return Category.OTHER


def _build_report(data: ReportIn) -> Report:
    loc_present = has_location(data.lat, data.lng)
    time_present = data.claimed_time is not None
    return Report(
        id=_new_id("rep"),
        reporter_id=data.reporter_id,
        category=_cat(data.category),
        text=data.text,
        lat=data.lat,
        lng=data.lng,
        named_location=data.named_location,
        claimed_time=data.claimed_time,
        captured_offline_at=data.captured_offline_at,
        received_at=utcnow(),
        severity_claimed=max(1, min(5, data.severity_claimed)),
        photo_hash=data.photo_hash,
        location_state=FieldState.PRESENT if loc_present else FieldState.MISSING,
        time_state=FieldState.PRESENT if time_present else FieldState.MISSING,
        sync_state=SyncState.DELAYED_SYNC if data.captured_offline_at else SyncState.SYNCED,
        truth_label=data.truth_label,
    )


async def _broadcast_incident(inc_id: str, event: str = "incident.update") -> None:
    inc = STORE.incidents.get(inc_id)
    if inc:
        await manager.broadcast({"event": event, "incident": incident_summary(inc)})


# --- Ingestion ------------------------------------------------------------

@app.post("/api/v1/reports")
async def create_report(data: ReportIn):
    with STORE.lock:
        report = _build_report(data)
        inc = pipeline.ingest_report(STORE, report, CFG)
        STORE.log("report", report.id, data.reporter_id, "citizen", f"ingested -> {inc.id}")
    await _broadcast_incident(inc.id)
    return {"report_id": report.id, "incident_id": inc.id,
            "location_state": report.location_state.value,
            "incident": incident_summary(inc)}


@app.post("/api/v1/reports/batch")
async def create_reports_batch(items: list[ReportIn]):
    touched: set[str] = set()
    with STORE.lock:
        for data in items:
            report = _build_report(data)
            inc = pipeline.ingest_report(STORE, report, CFG)
            touched.add(inc.id)
    for inc_id in touched:
        await _broadcast_incident(inc_id)
    return {"ingested": len(items), "incidents_touched": len(touched)}


@app.post("/api/v1/feeds/official")
async def official_feed(data: OfficialIn):
    with STORE.lock:
        ev = OfficialEvent(
            id=_new_id("off"),
            category=_cat(data.category),
            lat=data.lat,
            lng=data.lng,
            source_type=data.source_type,
            observed_at=data.observed_at or utcnow(),
            strength=data.strength,
        )
        pipeline.add_official_event(STORE, ev, CFG)
        STORE.log("official_event", ev.id, "feed", "system", f"{ev.source_type}")
    await manager.broadcast({"event": "official.update"})
    return {"official_event_id": ev.id}


# --- Verification ---------------------------------------------------------

@app.post("/api/v1/incidents/{incident_id}/verify")
async def verify(incident_id: str, data: VerifyIn):
    with STORE.lock:
        if incident_id not in STORE.incidents:
            raise HTTPException(404, "incident not found")
        try:
            action = VerifyAction(data.action)
        except ValueError:
            raise HTTPException(400, "invalid action")
        try:
            role = Role(data.actor_role)
        except ValueError:
            role = Role.RESPONDER
        ev = VerificationEvent(
            id=_new_id("ver"),
            incident_id=incident_id,
            actor_id=data.actor_id,
            actor_role=role,
            action=action,
            note=data.note,
            lat=data.lat,
            lng=data.lng,
            captured_offline_at=data.captured_offline_at,
        )
        inc = pipeline.add_verification(STORE, ev, CFG)
        STORE.log("incident", incident_id, data.actor_id, role.value,
                  f"{action.value} -> {inc.verification_state.value}")
    await _broadcast_incident(incident_id, "incident.verified")
    return {"verification_id": ev.id, "incident": incident_detail(inc)}


# --- Publish gate ---------------------------------------------------------

@app.post("/api/v1/incidents/{incident_id}/publish")
async def publish(incident_id: str, data: PublishIn):
    with STORE.lock:
        inc = STORE.incidents.get(incident_id)
        if not inc:
            raise HTTPException(404, "incident not found")
        if not is_publishable(inc) and not data.override:
            raise HTTPException(
                409,
                {"error": "not publishable",
                 "reason": f"state={inc.verification_state.value}, freshness={inc.freshness_state.value}",
                 "hint": "Only VERIFIED & non-stale incidents publish; use override with justification."},
            )
        if not is_publishable(inc) and data.override and not data.justification:
            raise HTTPException(400, "override requires justification")
        inc.published = True
        change = "published" + (f" (OVERRIDE: {data.justification})" if data.override else "")
        STORE.log("incident", incident_id, data.actor_id, data.actor_role, change)
    await _broadcast_incident(incident_id, "incident.published")
    return {"published": True, "override": data.override, "incident": incident_summary(inc)}


# --- Queries / dashboard --------------------------------------------------

@app.get("/api/v1/incidents")
def list_incidents(
    role: str | None = None,
    state: str | None = Query(None, description="filter by verification_state"),
    fresh_only: bool = False,
    verified_only: bool = False,
    sort: str = "priority",
):
    incs = list(STORE.incidents.values())
    if state:
        incs = [i for i in incs if i.verification_state.value == state]
    if verified_only:
        incs = [i for i in incs if i.verification_state.value == "VERIFIED"]
    if fresh_only:
        incs = [i for i in incs if i.freshness_state.value in ("FRESH", "RECENT", "AGING")]
    # PIO sees only verified, non-stale
    if role == "pio":
        incs = [i for i in incs if is_publishable(i) or i.published]
    reverse = True
    key = {
        "priority": lambda i: i.priority,
        "confidence": lambda i: i.confidence,
        "recent": lambda i: i.last_evidence_at,
    }.get(sort, lambda i: i.priority)
    incs.sort(key=key, reverse=reverse)
    return {"count": len(incs), "incidents": [incident_summary(i) for i in incs]}


@app.get("/api/v1/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = STORE.incidents.get(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return incident_detail(inc)


@app.get("/api/v1/incidents/{incident_id}/evidence")
def get_evidence(incident_id: str):
    inc = STORE.incidents.get(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    reports = STORE.reports_for(incident_id)
    verifs = STORE.verifications_for(incident_id)
    return {
        "incident": incident_detail(inc),
        "reports": [report_out(r) for r in reports],
        "verifications": [verification_out(v) for v in verifs],
        "why_this_score": inc.breakdown.as_dict(),
        "official_match": inc.official_match,
        "reporters": [
            {"id": r.reporter_id,
             "reputation": round(STORE.reporters[r.reporter_id].reputation, 2)
             if r.reporter_id in STORE.reporters else None}
            for r in reports
        ],
    }


# --- Offline sync (idempotent, capture-time truth) ------------------------

@app.post("/api/v1/sync")
async def sync(data: SyncIn):
    results = []
    touched: set[str] = set()
    with STORE.lock:
        for act in data.actions:
            if STORE.seen_sync(act.client_uuid):
                results.append({"client_uuid": act.client_uuid, "status": "duplicate"})
                continue
            try:
                if act.kind == "report":
                    rin = ReportIn(**act.payload)
                    report = _build_report(rin)
                    report.sync_state = SyncState.DELAYED_SYNC
                    inc = pipeline.ingest_report(STORE, report, CFG)
                    touched.add(inc.id)
                    results.append({"client_uuid": act.client_uuid, "status": "applied",
                                    "incident_id": inc.id})
                elif act.kind == "verify":
                    vin = VerifyIn(**{k: v for k, v in act.payload.items() if k != "incident_id"})
                    inc_id = act.payload.get("incident_id")
                    if inc_id not in STORE.incidents:
                        results.append({"client_uuid": act.client_uuid, "status": "conflict",
                                        "reason": "incident missing"})
                        continue
                    role = Role(vin.actor_role) if vin.actor_role in Role._value2member_map_ else Role.RESPONDER
                    ev = VerificationEvent(
                        id=_new_id("ver"), incident_id=inc_id, actor_id=vin.actor_id,
                        actor_role=role, action=VerifyAction(vin.action), note=vin.note,
                        captured_offline_at=vin.captured_offline_at,
                    )
                    inc = pipeline.add_verification(STORE, ev, CFG)
                    touched.add(inc.id)
                    results.append({"client_uuid": act.client_uuid, "status": "applied",
                                    "incident_id": inc_id})
                else:
                    results.append({"client_uuid": act.client_uuid, "status": "conflict",
                                    "reason": "unknown kind"})
                    continue
                STORE.mark_sync(act.client_uuid)
            except Exception as exc:  # noqa: BLE001
                results.append({"client_uuid": act.client_uuid, "status": "error", "reason": str(exc)})
    for inc_id in touched:
        await _broadcast_incident(inc_id, "incident.synced")
    return {"results": results}


# --- Audit ----------------------------------------------------------------

@app.get("/api/v1/audit")
def audit(entity_id: str | None = None, limit: int = 200):
    entries = STORE.audit
    if entity_id:
        entries = [e for e in entries if e.entity_id == entity_id]
    entries = entries[-limit:][::-1]
    return {"count": len(entries), "entries": [
        {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id,
         "actor_id": e.actor_id, "actor_role": e.actor_role, "change": e.change,
         "created_at": e.created_at.isoformat()} for e in entries]}


# --- Admin / lifecycle ----------------------------------------------------

@app.post("/api/v1/admin/reset")
def reset():
    STORE.reset()
    return {"reset": True}


@app.post("/api/v1/admin/refresh-freshness")
async def refresh_freshness():
    with STORE.lock:
        changed = pipeline.refresh_freshness(STORE, CFG)
    for inc_id in changed:
        await _broadcast_incident(inc_id, "incident.freshness")
    return {"changed": changed}


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "incidents": len(STORE.incidents), "reports": len(STORE.reports)}


# --- Metrics & experiment -------------------------------------------------

@app.get("/api/v1/metrics/experiment")
def metrics_experiment(seeds: int = 20):
    from metrics.experiment import run_experiment

    start = 42
    return run_experiment(seeds=range(start, start + max(1, seeds)), cfg=CFG)


@app.get("/api/v1/metrics/live")
def metrics_live():
    """Live operational metrics for the current in-memory session."""
    incs = list(STORE.incidents.values())
    verified = [i for i in incs if i.verification_state.value == "VERIFIED"]
    hp_verified = [i for i in verified if i.priority >= 40.0]
    by_state: dict[str, int] = {}
    for i in incs:
        by_state[i.verification_state.value] = by_state.get(i.verification_state.value, 0) + 1
    by_fresh: dict[str, int] = {}
    for i in incs:
        by_fresh[i.freshness_state.value] = by_fresh.get(i.freshness_state.value, 0) + 1
    return {
        "reports": len(STORE.reports),
        "incidents": len(incs),
        "verified": len(verified),
        "verified_high_priority": len(hp_verified),
        "manipulation_flagged": sum(1 for i in incs if i.manipulation_flag),
        "published": sum(1 for i in incs if i.published),
        "by_verification_state": by_state,
        "by_freshness_state": by_fresh,
    }


# --- Scenario replay (drives the demo & dashboard) ------------------------

@app.post("/api/v1/admin/replay")
async def replay(seed: int = 42, compress: float = 0.02):
    """Load a simulated storm scenario into the live store for the dashboard.

    `compress` scales scenario time so a 90-min scenario replays quickly while
    preserving ordering. Reports keep simulated claimed_time for clustering.
    """
    from datetime import timedelta

    from simulator.generate import build_storm_scenario

    STORE.reset()
    sc = build_storm_scenario(seed=seed)
    base = utcnow()
    touched: set[str] = set()

    # ingest reports in offset order with simulated timestamps
    for i, r in enumerate(sc.reports):
        ts = base + timedelta(seconds=r.offset_s * compress)
        lat = None if r.drop_location else r.lat
        lng = None if r.drop_location else r.lng
        rep = Report(
            id=_new_id("rep"),
            reporter_id=r.reporter_id,
            category=_cat(r.category),
            text=r.text, lat=lat, lng=lng, named_location=r.named_location,
            claimed_time=None if r.drop_time else ts, received_at=ts,
            severity_claimed=max(1, r.severity_claimed),
            location_state=FieldState.PRESENT if has_location(lat, lng) else FieldState.MISSING,
            time_state=FieldState.PRESENT if not r.drop_time else FieldState.MISSING,
            truth_label=r.truth_label,
        )
        inc = pipeline.ingest_report(STORE, rep, CFG)
        touched.add(inc.id)

    # official corroboration events
    for e in sc.official_events:
        ev = OfficialEvent(
            id=_new_id("off"), category=_cat(e["category"]),
            lat=e["lat"], lng=e["lng"], source_type=e["source_type"], observed_at=utcnow(),
        )
        pipeline.add_official_event(STORE, ev, CFG)

    STORE.log("scenario", sc.name, "system", "system", f"replayed seed={seed}")
    for inc_id in touched:
        await _broadcast_incident(inc_id, "scenario.loaded")
    return {"loaded": sc.name, "seed": seed, "reports": len(sc.reports),
            "incidents": len(STORE.incidents),
            "true_incidents": [{"id": t.id, "stop": t.stop, "category": t.category,
                                "high_priority": t.high_priority} for t in sc.truth]}


# --- WebSocket ------------------------------------------------------------

@app.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:  # noqa: BLE001
        manager.disconnect(websocket)


# background freshness ticker
@app.on_event("startup")
async def _start_ticker():
    async def tick():
        while True:
            await asyncio.sleep(30)
            with STORE.lock:
                changed = pipeline.refresh_freshness(STORE, CFG)
            for inc_id in changed:
                await _broadcast_incident(inc_id, "incident.freshness")

    asyncio.create_task(tick())
