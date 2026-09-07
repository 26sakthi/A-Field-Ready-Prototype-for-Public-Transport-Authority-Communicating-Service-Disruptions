"""Independence assessment: resist manipulation and double-counting.

50 retweets of one claim are not 50 sources. We count *independent* reporters,
collapse near-duplicate text, and detect coordinated bursts.
"""
from __future__ import annotations

from .config import EngineConfig
from .domain import Report


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().split() if t}


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def independent_sources(reports: list[Report], cfg: EngineConfig) -> int:
    """Count distinct reporters, collapsing near-duplicate text into one source.

    Each distinct reporter counts once. Additionally, if many reporters post
    near-identical text (copy/paste campaign), those are collapsed to a single
    effective source.
    """
    by_reporter: dict[str, Report] = {}
    for r in reports:
        # keep the earliest report per reporter as representative
        cur = by_reporter.get(r.reporter_id)
        if cur is None or r.received_at < cur.received_at:
            by_reporter[r.reporter_id] = r

    reps = list(by_reporter.values())
    # collapse near-duplicate text across reporters
    effective: list[Report] = []
    for r in reps:
        if any(jaccard(r.text, e.text) >= cfg.dup_jaccard for e in effective):
            continue
        effective.append(r)
    return len(effective)


def detect_burst(reports: list[Report], cfg: EngineConfig) -> bool:
    """Coordinated-burst heuristic.

    The signature of a manipulation campaign is *many near-identical posts from
    very few authors in a tight window* -- copy/paste amplification. We detect it
    by grouping reports on near-duplicate text and checking any group for
    high volume + few distinct reporters + a short time span. Keying on text
    (not just temporal density) keeps this robust when unrelated high-volume
    traffic is present in the same cluster.
    """
    if len(reports) < cfg.burst_count:
        return False

    window = cfg.burst_window_min * 60.0
    groups: list[list[Report]] = []
    for r in reports:
        placed = False
        for g in groups:
            if jaccard(r.text, g[0].text) >= cfg.dup_jaccard:
                g.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])

    for g in groups:
        if len(g) < cfg.burst_count:
            continue
        reporters = {r.reporter_id for r in g}
        if len(reporters) > cfg.burst_distinct_reporters:
            continue
        times = sorted(r.received_at for r in g)
        span = (times[-1] - times[0]).total_seconds()
        if span <= window:
            return True
    return False
