"""Priority = severity x confidence x impact.

Impact blends category criticality with severity so the triage queue floats
verified, high-severity, high-impact incidents to the top.
"""
from __future__ import annotations

from .config import EngineConfig
from .domain import Category


def compute_priority(
    severity: int,
    confidence: float,
    category: Category,
    cfg: EngineConfig,
) -> float:
    severity_norm = max(1, min(5, severity)) / 5.0
    confidence_norm = confidence / 100.0
    criticality = cfg.criticality.get(category, 0.4)
    impact_norm = 0.5 * criticality + 0.5 * severity_norm
    return round(100.0 * severity_norm * confidence_norm * impact_norm, 1)


def is_high_priority(priority: float, threshold: float = 40.0) -> bool:
    return priority >= threshold
