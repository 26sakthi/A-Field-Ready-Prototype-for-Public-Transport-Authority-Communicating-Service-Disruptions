"""Clustering: attach a report to an existing incident or seed a new one.

A report joins an open incident when category is compatible, it is within the
spatial radius, and within the temporal window. Reports with a MISSING location
are never spatially clustered -- they attach as unlocated evidence and are
flagged for enrichment (PRD edge case: missing location/time).
"""
from __future__ import annotations

from typing import Iterable, Optional

from .config import EngineConfig
from .domain import COMPATIBLE, Category, FieldState, Incident, Report
from .geo import haversine_m


def _category_compatible(a: Category, b: Category) -> bool:
    return b in COMPATIBLE.get(a, {a})


def find_incident_for(
    report: Report,
    incidents: Iterable[Incident],
    cfg: EngineConfig,
) -> Optional[Incident]:
    """Return the best open incident this report belongs to, or None."""
    if report.location_state == FieldState.MISSING:
        return None

    best: Optional[Incident] = None
    best_dist = float("inf")
    ref_time = report.claimed_time or report.received_at

    for inc in incidents:
        if inc.verification_state in ("DEBUNKED",):
            continue
        if not _category_compatible(inc.category, report.category):
            continue
        if inc.center_lat is None or report.lat is None:
            continue
        dist = haversine_m(inc.center_lat, inc.center_lng, report.lat, report.lng)
        if dist > cfg.radius_m:
            continue
        # Temporal window is anchored to the incident's ONSET, not its last
        # evidence -- otherwise a steady trickle of nearby reports would roll the
        # window forward forever and absorb unrelated traffic (over-clustering).
        dt_min = abs((ref_time - inc.first_reported_at).total_seconds()) / 60.0
        if dt_min > cfg.time_window_min:
            continue
        if dist < best_dist:
            best, best_dist = inc, dist
    return best


def update_center(inc: Incident, reports: list[Report]) -> None:
    """Recompute incident centroid from its located reports."""
    located = [r for r in reports if r.lat is not None and r.lng is not None]
    if not located:
        return
    inc.center_lat = sum(r.lat for r in located) / len(located)
    inc.center_lng = sum(r.lng for r in located) / len(located)
