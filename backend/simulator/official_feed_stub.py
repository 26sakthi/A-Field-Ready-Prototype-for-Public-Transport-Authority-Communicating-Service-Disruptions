"""Official-feed integration STUB.

Stands in for real transit feeds (AVL vehicle-gap detection, weather alerts, IoT
water sensors). In a real deployment these would be adapters over GTFS-RT / vendor
APIs; here they emit synthetic corroborating events on the same schedule the
scenario prescribes.
"""
from __future__ import annotations

from engine.config import EngineConfig
from engine.domain import Category, OfficialEvent, utcnow
from engine import pipeline


def emit_official(store, category: str, lat: float, lng: float,
                  source_type: str, cfg: EngineConfig) -> OfficialEvent:
    import uuid

    try:
        cat = Category(category)
    except ValueError:
        cat = Category.OTHER
    ev = OfficialEvent(
        id=f"off_{uuid.uuid4().hex[:8]}",
        category=cat, lat=lat, lng=lng, source_type=source_type,
        observed_at=utcnow(),
    )
    pipeline.add_official_event(store, ev, cfg)
    return ev
