"""Core domain types for the VeriTransit verification engine.

Pure data structures + enums, independent of storage and web framework.
Every state is an explicit enum value -- there is no implicit "unknown".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Enumerations (explicit states, never null) ---------------------------

class Category(str, Enum):
    FLOOD = "flood"
    FIRE = "fire"
    BREAKDOWN = "breakdown"
    CROWDING = "crowding"
    DELAY = "delay"
    SAFETY = "safety"
    OTHER = "other"


# categories that may cluster together (compatible real-world events)
COMPATIBLE = {
    Category.FLOOD: {Category.FLOOD, Category.SAFETY},
    Category.FIRE: {Category.FIRE, Category.SAFETY},
    Category.BREAKDOWN: {Category.BREAKDOWN, Category.DELAY},
    Category.DELAY: {Category.DELAY, Category.BREAKDOWN, Category.CROWDING},
    Category.CROWDING: {Category.CROWDING, Category.DELAY, Category.SAFETY},
    Category.SAFETY: {Category.SAFETY},
    Category.OTHER: {Category.OTHER},
}


class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    CORROBORATING = "CORROBORATING"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    DEBUNKED = "DEBUNKED"


class FreshnessState(str, Enum):
    FRESH = "FRESH"      # < 5 min
    RECENT = "RECENT"    # 5-15 min
    AGING = "AGING"      # 15-45 min
    STALE = "STALE"      # past category staleness threshold
    EXPIRED = "EXPIRED"  # past useful life


class FieldState(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    LOW_ACCURACY = "LOW_ACCURACY"


class SyncState(str, Enum):
    SYNCED = "SYNCED"
    QUEUED = "QUEUED"
    DELAYED_SYNC = "DELAYED_SYNC"


class VerifyAction(str, Enum):
    CONFIRM = "CONFIRM"
    DENY = "DENY"
    NEEDS_MORE = "NEEDS_MORE"


class Role(str, Enum):
    RESPONDER = "responder"
    OFFICER = "officer"
    DECISION_MAKER = "decision_maker"
    PIO = "pio"
    ANALYST = "analyst"


# --- Entities --------------------------------------------------------------

@dataclass
class Reporter:
    id: str
    channel: str = "app"
    reputation: float = 0.5          # behavioural, decaying, 0..1
    confirmed_count: int = 0
    debunked_count: int = 0
    first_seen: datetime = field(default_factory=utcnow)


@dataclass
class Report:
    id: str
    reporter_id: str
    category: Category
    text: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    named_location: str = ""
    claimed_time: Optional[datetime] = None
    received_at: datetime = field(default_factory=utcnow)
    captured_offline_at: Optional[datetime] = None
    severity_claimed: int = 3        # 1..5
    photo_hash: str = ""
    incident_id: Optional[str] = None
    location_state: FieldState = FieldState.PRESENT
    time_state: FieldState = FieldState.PRESENT
    sync_state: SyncState = SyncState.SYNCED
    # ground-truth label carried only for simulated data / experiments
    truth_label: Optional[str] = None    # e.g. "true:<id>", "noise", "misinfo"


@dataclass
class VerificationEvent:
    id: str
    incident_id: str
    actor_id: str
    actor_role: Role
    action: VerifyAction
    note: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    created_at: datetime = field(default_factory=utcnow)
    captured_offline_at: Optional[datetime] = None


@dataclass
class OfficialEvent:
    id: str
    category: Category
    lat: float
    lng: float
    source_type: str          # avl_gap | weather | sensor
    observed_at: datetime = field(default_factory=utcnow)
    strength: float = 1.0


@dataclass
class ConfidenceBreakdown:
    corroboration: float = 0.0
    reputation: float = 0.0
    responder: float = 0.0
    official: float = 0.0
    recency: float = 0.0
    total: float = 0.0

    def as_dict(self) -> dict:
        return {
            "corroboration": round(self.corroboration, 3),
            "reputation": round(self.reputation, 3),
            "responder": round(self.responder, 3),
            "official": round(self.official, 3),
            "recency": round(self.recency, 3),
            "total": round(self.total, 1),
        }


@dataclass
class Incident:
    id: str
    category: Category
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    severity: int = 3
    confidence: float = 0.0
    priority: float = 0.0
    verification_state: VerificationState = VerificationState.UNVERIFIED
    freshness_state: FreshnessState = FreshnessState.FRESH
    manipulation_flag: bool = False
    publishable: bool = False
    published: bool = False
    first_reported_at: datetime = field(default_factory=utcnow)
    last_evidence_at: datetime = field(default_factory=utcnow)
    report_ids: list[str] = field(default_factory=list)
    breakdown: ConfidenceBreakdown = field(default_factory=ConfidenceBreakdown)
    independent_sources: int = 0
    confirms: int = 0
    denies: int = 0
    official_match: bool = False


@dataclass
class AuditEntry:
    id: str
    entity_type: str
    entity_id: str
    actor_id: str
    actor_role: str
    change: str
    created_at: datetime = field(default_factory=utcnow)
