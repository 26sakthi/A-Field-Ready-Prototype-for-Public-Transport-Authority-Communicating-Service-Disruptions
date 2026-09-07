"""Pydantic request/response models + serialization helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from engine.domain import Incident, Report, VerificationEvent


class ReportIn(BaseModel):
    reporter_id: str
    category: str
    text: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    named_location: str = ""
    claimed_time: Optional[datetime] = None
    captured_offline_at: Optional[datetime] = None
    severity_claimed: int = 3
    channel: str = "app"
    photo_hash: str = ""
    truth_label: Optional[str] = None


class VerifyIn(BaseModel):
    actor_id: str
    actor_role: str = "responder"
    action: str  # CONFIRM | DENY | NEEDS_MORE
    note: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    captured_offline_at: Optional[datetime] = None


class OfficialIn(BaseModel):
    category: str
    lat: float
    lng: float
    source_type: str = "sensor"
    observed_at: Optional[datetime] = None
    strength: float = 1.0


class PublishIn(BaseModel):
    actor_id: str
    actor_role: str = "pio"
    override: bool = False
    justification: str = ""


class SyncAction(BaseModel):
    client_uuid: str
    kind: str  # "report" | "verify"
    payload: dict


class SyncIn(BaseModel):
    actions: list[SyncAction]


def incident_summary(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "category": inc.category.value,
        "center_lat": inc.center_lat,
        "center_lng": inc.center_lng,
        "severity": inc.severity,
        "confidence": round(inc.confidence, 1),
        "priority": inc.priority,
        "verification_state": inc.verification_state.value,
        "freshness_state": inc.freshness_state.value,
        "manipulation_flag": inc.manipulation_flag,
        "publishable": inc.publishable,
        "published": inc.published,
        "independent_sources": inc.independent_sources,
        "confirms": inc.confirms,
        "denies": inc.denies,
        "official_match": inc.official_match,
        "report_count": len(inc.report_ids),
        "first_reported_at": inc.first_reported_at.isoformat(),
        "last_evidence_at": inc.last_evidence_at.isoformat(),
    }


def report_out(r: Report) -> dict:
    return {
        "id": r.id,
        "reporter_id": r.reporter_id,
        "category": r.category.value,
        "text": r.text,
        "lat": r.lat,
        "lng": r.lng,
        "named_location": r.named_location,
        "severity_claimed": r.severity_claimed,
        "claimed_time": (r.claimed_time.isoformat() if r.claimed_time else None),
        "received_at": r.received_at.isoformat(),
        "location_state": r.location_state.value,
        "time_state": r.time_state.value,
        "sync_state": r.sync_state.value,
    }


def verification_out(v: VerificationEvent) -> dict:
    return {
        "id": v.id,
        "actor_id": v.actor_id,
        "actor_role": v.actor_role.value if hasattr(v.actor_role, "value") else v.actor_role,
        "action": v.action.value,
        "note": v.note,
        "created_at": v.created_at.isoformat(),
        "captured_offline_at": (v.captured_offline_at.isoformat() if v.captured_offline_at else None),
    }


def incident_detail(inc: Incident) -> dict:
    d = incident_summary(inc)
    d["breakdown"] = inc.breakdown.as_dict()
    return d
