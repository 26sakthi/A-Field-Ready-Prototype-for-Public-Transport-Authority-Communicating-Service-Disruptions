# 🧪 Testing Guide — Unit Tests, Integration Tests & Error Boundaries

| | |
|---|---|
| **Document** | Testing Guide |
| **Version** | 1.0 |
| **Date** | 2026-09-29 |
| **Implementation** | [`backend/tests/`](../backend/tests/) |

---

## 1. Running the Test Suite

```bash
cd backend
# Activate virtualenv first
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux

# Run all tests (quiet)
python -m pytest -q

# Run with full output (verbose)
python -m pytest -v

# Run a specific file
python -m pytest tests/test_engine.py -v
python -m pytest tests/test_edge_cases.py -v
python -m pytest tests/test_independence_dedup_stress.py -v
```

**Expected result — all 17 tests pass in < 0.15 s:**
```
tests/test_edge_cases.py            .....   [ 29%]
tests/test_engine.py                .......  [ 70%]
tests/test_independence_dedup_stress.py .....  [100%]

17 passed in 0.09s
```

---

## 2. Test Files & Coverage Map

| File | Tests | What it covers |
|---|---|---|
| [`test_engine.py`](../backend/tests/test_engine.py) | 7 | Core engine unit tests |
| [`test_edge_cases.py`](../backend/tests/test_edge_cases.py) | 5 | PRD edge-case integration tests |
| [`test_independence_dedup_stress.py`](../backend/tests/test_independence_dedup_stress.py) | 5 | Synthetic stress tests |

---

## 3. Unit Tests — `test_engine.py`

Each test exercises a single, pure engine function in isolation using an in-memory `Store`.

### `test_two_independent_reports_corroborate`
**What it tests:** Two reports from different reporters with distinct texts cluster into one incident and produce `independent_sources == 2` and `verification_state == CORROBORATING`.

**Why it matters:** Validates the baseline corroboration path — the most common route to `CORROBORATING`.

**Error boundaries:**
- If the same reporter submits both → `independent_sources` must remain `1` (tested separately).
- If texts are near-identical (Jaccard ≥ 0.90) → collapsed to `1` effective source.

---

### `test_same_reporter_does_not_corroborate`
**What it tests:** Two reports with different text from the **same** `reporter_id` yield `independent_sources == 1` and `verification_state == UNVERIFIED`.

**Error boundary:** Reporter deduplication must apply even when text is unique — the identity check (`reporter_id`) runs before text similarity.

---

### `test_duplicate_text_collapses_to_one_source`
**What it tests:** Two distinct reporters submitting identical text (`"evacuate now everyone"`) are collapsed to `independent_sources == 1` via Jaccard similarity (J = 1.00 ≥ threshold 0.90).

**Error boundary:** Ensures 50 copy-paste retweets from 50 distinct accounts never count as 50 independent sources.

---

### `test_responder_confirm_verifies`
**What it tests:** After two corroborating reports, a `VerifyAction.CONFIRM` from a `Role.RESPONDER` transitions `verification_state` to `VERIFIED` and lifts confidence above 45.

**Error boundary:** Responder signal (`w_v = 0.35`) is the strongest component; confirmation without enough corroboration alone is allowed when a responder acts directly.

---

### `test_confidence_breakdown_sums_to_total`
**What it tests:** The sum of the five signal components (`corroboration + reputation + responder + official + recency`) equals `breakdown.total` within a 0.5 rounding tolerance.

**Error boundary (NFR-3 explainability):** If breakdown components do not sum to the displayed total, the "why this score" drill-down gives misleading information to officers.

---

### `test_priority_orders_high_severity_confident_first`
**What it tests:** `priority(severity=5, confidence=90, FLOOD) > priority(severity=2, confidence=40, DELAY)`.

**Error boundary:** The triage queue depends on priority ordering; inverted ordering would surface low-severity noise above critical incidents.

---

### `test_new_incident_when_far_away`
**What it tests:** Two reports at coordinates ~20 km apart (lat `13.08` vs `13.20`) each seed their own incident (`len(incidents) == 2`).

**Error boundary:** Haversine distance must exceed `R_spatial = 250 m` to create a new incident; floating-point precision in `haversine_m` is exercised here.

---

## 4. Edge-Case Integration Tests — `test_edge_cases.py`

These tests exercise the full pipeline (ingest → independence → confidence → state machine) against the five PRD edge cases.

### EC-1 · `test_conflicting_reports_go_disputed`
- **Scenario:** Two field responders CONFIRM then DENY the same incident.
- **Expected:** `verification_state == DISPUTED`.
- **Error boundary:** Mixed signals must not resolve to VERIFIED or DEBUNKED prematurely.

### EC-2 · `test_stale_then_expired_over_time`
- **Scenario:** Reports timestamped 200 min ago (past `expire_factor × tau` for FLOOD = 270 min).
- **Expected:** `freshness_state in (STALE, EXPIRED)` and `publishable == False`.
- **Error boundary:** Stale/expired incidents are blocked from the Comms Board publish gate. A freshness calculation bug would allow stale incidents to be published.

### EC-3 · `test_misinformation_burst_flagged_and_not_verified`
- **Scenario:** 12 identical posts from 2 bot accounts within seconds.
- **Expected:** `manipulation_flag == True`, `verification_state != VERIFIED`, `confidence < 50`.
- **Error boundary:** The corroboration penalty (`× 0.20`) must prevent burst spam from reaching the VERIFIED state without a responder override.

### EC-4 · `test_missing_location_not_clustered_but_retained`
- **Scenario:** Report submitted with `lat=None, lng=None, location_state=MISSING`.
- **Expected:** Report stored, `incident.center_lat == None` (not placed at `(0, 0)`).
- **Error boundary:** Missing location must not corrupt spatial clustering or produce `(0, 0)` ghost incidents on the Situation Map.

### EC-5 · `test_delayed_sync_uses_capture_time_not_receipt_time`
- **Scenario:** Offline capture 20 min ago, synced now. `captured_offline_at = utcnow() - 20m`.
- **Expected:** `incident.last_evidence_at` is ≥ 19 min in the past — uses capture time, not receipt time.
- **Error boundary:** Scoring against sync time would incorrectly inflate recency for old offline actions, unfairly boosting confidence.

---

## 5. Synthetic Stress Tests — `test_independence_dedup_stress.py`

### SS-1 · `test_burst_coordinated_spam_collapses_and_flags_manipulation`
- **Setup:** 25 identical posts from 2 bot IDs within 45 s, plus 2 genuine distinct reports.
- **Assertions:**
  - `detect_burst() == True` and `manipulation_flag == True`
  - `independent_sources == 3` (25 spam → 1 collapsed, 2 genuine = 3)
  - `confidence < 60.0` (burst penalty applied)

### SS-2 · `test_duplicate_coords_across_split_timestamps_seed_separate_incidents`
- **Setup:** Reports at identical GPS coordinates at `t₀`, `t₀ + 35 min`, and `t₀ + 120 min`.
- **Assertions:** 3 separate incidents created — temporal window anchored to onset prevents cross-window merging.

### SS-3 · `test_paraphrased_spam_jaccard_deduplication`
- **Setup:** 5 high-overlap phrase variants (Jaccard ≈ 0.90+) from 5 distinct accounts.
- **Assertions:** `independent_sources == 1` — all variants collapsed to a single effective source.

### SS-4 · `test_cross_category_conflicting_reports_isolate_into_separate_clusters`
- **Setup:** FLOOD, FIRE, and CROWDING reports at identical coordinates and timestamp.
- **Assertions:** 3 distinct incidents created — incompatible categories never merge.

### SS-5 · `test_missing_location_high_volume_burst_isolation`
- **Setup:** 15 reports with `location_state=MISSING` in rapid succession.
- **Assertions:** `incident.center_lat == None`, all 15 reports retained in store.

---

## 6. How to Write New Tests

All tests use a lightweight in-memory `Store` class defined locally (no database setup required):

```python
from engine.config import EngineConfig
from engine.domain import Category, Report, utcnow
from engine import pipeline

CFG = EngineConfig()

class Store:
    def __init__(self):
        self.reports, self.incidents, self.reporters = {}, {}, {}
        self.verifications, self.official_events = {}, {}

    def reports_for(self, iid):
        return [r for r in self.reports.values() if r.incident_id == iid]

    def verifications_for(self, iid):
        return [v for v in self.verifications.values() if v.incident_id == iid]

def make_report(rid, reporter, text="flood at station", cat=Category.FLOOD,
                lat=13.08, lng=80.27, sev=4, dt=None):
    t = dt or utcnow()
    return Report(id=rid, reporter_id=reporter, category=cat, lat=lat, lng=lng,
                  text=text, severity_claimed=sev, claimed_time=t, received_at=t)

def test_my_new_case():
    s = Store()
    inc = pipeline.ingest_report(s, make_report("r1", "user_a"), CFG)
    assert inc is not None
```

**Guidelines:**
- Keep tests stateless — create a fresh `Store()` per test.
- Use `utcnow() - timedelta(minutes=X)` to simulate aged reports for freshness tests.
- Parameterise with `@pytest.mark.parametrize` when sweeping threshold boundaries.
- Name tests `test_<what>_<expected_outcome>` for self-documenting test discovery.

---

## 7. Error Boundary Checklist

| Boundary | Tested In | Guard Mechanism |
|---|---|---|
| Duplicate reporter → no extra corroboration | `test_engine.py` | `by_reporter` deduplication in `independence.py` |
| Copy-paste text → single effective source | `test_engine.py`, SS-3 | Token Jaccard (J ≥ 0.90) collapsing |
| Burst spam → manipulation flag + penalty | EC-3, SS-1 | `detect_burst()` + `corr *= 0.20` |
| Missing location → no (0,0) ghost incident | EC-4, SS-5 | `FieldState.MISSING` bypasses spatial clustering |
| Offline capture time preserved | EC-5 | `captured_offline_at` used as `last_evidence_at` |
| Stale incident blocked from publish | EC-2 | `is_publishable()` gate in `states.py` |
| Conflicting responders → DISPUTED | EC-1 | Verification state machine in `states.py` |
| Cross-category isolation | SS-4 | `COMPATIBLE` category map in `cluster.py` |
| Temporal window anchored to onset | SS-2 | `inc.first_reported_at` anchor in `cluster.py` |
| Score breakdown sums to total | `test_engine.py` | `ConfidenceBreakdown.as_dict()` |
