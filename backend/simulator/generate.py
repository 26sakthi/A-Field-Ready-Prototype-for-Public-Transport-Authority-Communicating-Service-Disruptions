"""Scenario-based report simulator with ground-truth labels.

Generates a realistic mixed stream for a simulated disruption: true multi-reporter
incidents (some high-priority), duplicates, background noise, stale reports, and
coordinated misinformation bursts. Every report carries a hidden truth_label so
the experiment can measure precision/recall and TTVHP.

Deterministic given a seed -> reproducible validation dataset.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# A small synthetic transit network (stops with coordinates), city-agnostic.
STOPS = {
    "Central": (13.0827, 80.2707),
    "Riverside": (13.0900, 80.2600),
    "Harbour": (13.1000, 80.2900),
    "Uptown": (13.0700, 80.2500),
    "Market": (13.0600, 80.2800),
    "Airport Link": (12.9900, 80.1700),
    "Stadium": (13.0500, 80.2400),
    "Hillview": (13.1100, 80.2450),
}

CATEGORIES = ["flood", "fire", "breakdown", "crowding", "delay", "safety"]

TRUE_TEXTS = {
    "flood": ["water on the tracks at {stop}", "platform flooding at {stop}",
              "{stop} underpass flooded, knee deep"],
    "fire": ["smoke near {stop} station", "small fire at {stop} concourse"],
    "breakdown": ["train stalled just after {stop}", "{stop} service halted, doors stuck"],
    "crowding": ["dangerous crowding on {stop} platform", "{stop} platform overcrowded"],
    "delay": ["long delays at {stop}", "{stop} trains not moving"],
    "safety": ["medical emergency at {stop}", "unsafe situation at {stop}"],
}
NOISE_TEXTS = ["is the cafe at {stop} open?", "nice weather near {stop}",
               "lost my umbrella at {stop}", "{stop} looks busy today"]
MISINFO_TEXTS = ["BREAKING everyone evacuate {stop} NOW", "bomb at {stop} RT to warn",
                 "{stop} totally destroyed do not go"]


@dataclass
class SimReport:
    reporter_id: str
    category: str
    text: str
    lat: float | None
    lng: float | None
    named_location: str
    severity_claimed: int
    offset_s: int                 # seconds from scenario start
    truth_label: str              # "true:<id>" | "noise" | "misinfo"
    drop_location: bool = False
    drop_time: bool = False


@dataclass
class TrueIncident:
    id: str
    stop: str
    category: str
    severity: int
    high_priority: bool
    first_offset_s: int


@dataclass
class Scenario:
    name: str
    seed: int
    duration_min: int
    reports: list[SimReport] = field(default_factory=list)
    truth: list[TrueIncident] = field(default_factory=list)
    official_events: list[dict] = field(default_factory=list)


def _jitter(lat: float, lng: float, rng: random.Random, meters: float = 120.0):
    # ~degrees per meter
    dlat = (rng.uniform(-1, 1) * meters) / 111_000.0
    dlng = (rng.uniform(-1, 1) * meters) / 96_000.0
    return lat + dlat, lng + dlng


def build_storm_scenario(seed: int = 42) -> Scenario:
    """~90 min storm: 6 true incidents (2 high-priority), noise, 1 misinfo burst."""
    rng = random.Random(seed)
    sc = Scenario(name="storm", seed=seed, duration_min=90)

    true_specs = [
        ("Central", "flood", 5, True),
        ("Harbour", "flood", 4, True),
        ("Uptown", "breakdown", 3, False),
        ("Market", "crowding", 4, False),
        ("Stadium", "delay", 2, False),
        ("Hillview", "safety", 4, False),
    ]

    for idx, (stop, cat, sev, hp) in enumerate(true_specs):
        tid = f"T{idx+1}"
        first_off = rng.randint(30, 1500)
        sc.truth.append(TrueIncident(tid, stop, cat, sev, hp, first_off))
        base_lat, base_lng = STOPS[stop]
        # multiple independent reporters over a few minutes
        n_reporters = rng.randint(3, 6) if hp else rng.randint(2, 4)
        for k in range(n_reporters):
            lat, lng = _jitter(base_lat, base_lng, rng)
            text = rng.choice(TRUE_TEXTS[cat]).format(stop=stop)
            off = first_off + rng.randint(0, 300)
            sc.reports.append(SimReport(
                reporter_id=f"user_{tid}_{k}",
                category=cat, text=text, lat=lat, lng=lng, named_location=stop,
                severity_claimed=sev + rng.randint(-1, 0),
                offset_s=off, truth_label=f"true:{tid}",
                drop_location=(rng.random() < 0.08),
                drop_time=(rng.random() < 0.05),
            ))
        # official corroboration for the high-priority floods only
        if hp:
            sc.official_events.append({
                "category": cat, "lat": base_lat, "lng": base_lng,
                "source_type": "weather" if cat == "flood" else "sensor",
                "offset_s": first_off + rng.randint(120, 420),
            })

    # background noise -- high volume, matching the brief's ~600-report storm so
    # manual FIFO triage genuinely cannot keep up (this is the operational pain).
    for _ in range(540):
        stop = rng.choice(list(STOPS))
        base_lat, base_lng = STOPS[stop]
        lat, lng = _jitter(base_lat, base_lng, rng, meters=200)
        sc.reports.append(SimReport(
            reporter_id=f"noise_{rng.randint(0, 99999)}",
            category=rng.choice(CATEGORIES),
            text=rng.choice(NOISE_TEXTS).format(stop=stop),
            lat=lat, lng=lng, named_location=stop,
            severity_claimed=rng.randint(1, 2),
            offset_s=rng.randint(0, sc.duration_min * 60),
            truth_label="noise",
            drop_location=(rng.random() < 0.1),
        ))

    # coordinated misinformation burst (few reporters, many near-identical posts)
    misinfo_stop = "Riverside"
    m_lat, m_lng = STOPS[misinfo_stop]
    burst_off = 2400
    for i in range(14):
        reporter = f"bot_{i % 2}"   # only 2 distinct reporters -> burst
        sc.reports.append(SimReport(
            reporter_id=reporter,
            category="safety",
            text=MISINFO_TEXTS[0].format(stop=misinfo_stop),
            lat=m_lat, lng=m_lng, named_location=misinfo_stop,
            severity_claimed=5,
            offset_s=burst_off + i * 5,   # 14 posts within ~70s
            truth_label="misinfo",
        ))

    sc.reports.sort(key=lambda r: r.offset_s)
    return sc


def scenario_to_dicts(sc: Scenario, start: datetime | None = None) -> dict:
    """Materialise a scenario into API-ready payloads + labels (for dataset export)."""
    start = start or datetime.now(timezone.utc)
    reports = []
    for r in sc.reports:
        ts = start + timedelta(seconds=r.offset_s)
        reports.append({
            "reporter_id": r.reporter_id,
            "category": r.category,
            "text": r.text,
            "lat": None if r.drop_location else r.lat,
            "lng": None if r.drop_location else r.lng,
            "named_location": r.named_location,
            "claimed_time": None if r.drop_time else ts.isoformat(),
            "severity_claimed": max(1, r.severity_claimed),
            "truth_label": r.truth_label,
            "offset_s": r.offset_s,
        })
    official = [{**e, "start_offset": e["offset_s"]} for e in sc.official_events]
    truth = [vars(t) for t in sc.truth]
    return {"name": sc.name, "seed": sc.seed, "duration_min": sc.duration_min,
            "reports": reports, "official_events": official, "truth": truth}


if __name__ == "__main__":
    import json
    import sys

    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    data = scenario_to_dicts(build_storm_scenario(seed))
    print(json.dumps(data, indent=2, default=str))
