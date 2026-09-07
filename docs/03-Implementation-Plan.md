# Implementation Plan
## VeriTransit — Crowd-Report Verification & Confidence Dashboard

| | |
|---|---|
| **Document** | Implementation Plan |
| **Version** | 1.0 |
| **Date** | 2026-08-18 |
| **Companion docs** | `01-PRD.md`, `02-System-Architecture.md` |

This plan turns the PRD and Architecture into a buildable, sequenced prototype that produces **every deliverable in the brief**: requirements spec, prototype screens, core algorithm, API/integration stub, validation dataset, metric dashboard, limitations report, and a final demonstration — with a **baseline → target → measured → error analysis**.

---

## 1. Guiding Principle: Vertical Slices, Always Demoable

We build in **thin end-to-end slices** rather than horizontal layers, so at the end of every phase there is a *running* system, not a pile of parts. This directly serves the brief's demand that the output be "more than a concept presentation or isolated model notebook."

---

## 2. Tech Stack (locked for prototype)

- **Backend:** Python 3.11, FastAPI, Uvicorn, WebSockets, SQLModel/SQLAlchemy over **SQLite**.
- **Engine:** pure-Python package `engine/` (deterministic, unit-tested).
- **Frontend:** React 18 + Vite + TypeScript, MapLibre GL, Recharts, Dexie (IndexedDB), Workbox (Service Worker).
- **Simulator & metrics:** Python, seeded RNG (`numpy` optional), pandas for the experiment report.
- **Tooling:** pytest, ruff/black, vitest/RTL, a `Makefile`/`justfile` one-command run.

> Rationale in Architecture §10. Chosen for laptop-run, offline demo, and reproducible experiments.

---

## 3. Repository Layout

```
Nila Nila Odi Vaa/
├─ docs/                         # 01-PRD, 02-Architecture, 03-Implementation-Plan (this)
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # FastAPI app, routes, WS
│  │  ├─ api/                    # reports, incidents, verify, publish, sync, metrics, audit
│  │  ├─ models.py               # SQLModel tables + state enums
│  │  ├─ db.py
│  │  └─ deps.py                 # role-scoped session (simulated auth)
│  ├─ engine/
│  │  ├─ cluster.py              # spatial/temporal/category clustering
│  │  ├─ independence.py         # dedup, burst, reporter checks
│  │  ├─ confidence.py           # weighted signals + breakdown
│  │  ├─ priority.py
│  │  ├─ states.py               # verification + freshness state machines
│  │  └─ config.py               # weights, thresholds (R, T, τ)
│  ├─ simulator/
│  │  ├─ scenarios/              # YAML/JSON labelled scenarios
│  │  ├─ generate.py             # emits reports + ground-truth labels
│  │  └─ official_feed_stub.py
│  ├─ metrics/
│  │  ├─ experiment.py           # baseline vs system, TTVHP, P/R
│  │  └─ error_analysis.py
│  └─ tests/                     # unit + edge-case + integration
├─ frontend/
│  ├─ src/
│  │  ├─ views/                  # CaptureVerify, TriageQueue, SituationMap, CommsBoard, MetricsAdmin
│  │  ├─ components/             # ConfidenceBar, FreshnessPill, WhyThisScore, StateBadge, EvidenceDrawer
│  │  ├─ offline/                # dexie queue, sync manager, sw registration
│  │  └─ api/                    # REST + WS clients
│  └─ public/                    # PWA manifest, service worker
├─ data/
│  └─ validation/               # generated labelled dataset + results
└─ README.md                     # run instructions + demo script
```

---

## 4. Phased Delivery

### Phase 0 — Foundations & Baseline definition *(setup)*
**Goal:** repo scaffold + define the baseline we will beat.
- Scaffold backend, frontend, DB schema, one-command run.
- Implement the **baseline triage policy** to compare against: **FIFO/chronological, no clustering, no confidence** (simulates today's manual "read reports as they arrive"). Optionally a second baseline: **"act on all"** (everything treated as true).
- **Exit:** `POST /reports` persists; `GET /incidents` returns raw list; empty React shell loads.
- **Deliverable progress:** requirements spec (from PRD) referenced; baseline defined.

### Phase 1 — Core engine slice (clustering → confidence → priority)
**Goal:** the algorithmic heart, fully unit-tested and explainable.
- Implement `cluster.py`, `independence.py`, `confidence.py` (with breakdown), `priority.py`, `states.py`.
- Wire engine into ingestion so incidents form and score on each new report; push updates over WS.
- **Exit:** feeding a scripted stream produces correctly clustered, scored, prioritised incidents; `GET /incidents/{id}` returns the confidence breakdown.
- **Deliverable progress:** **core algorithm / rules** ✅.

### Phase 2 — Simulator & official-feed stub
**Goal:** realistic, *labelled* input for demos and experiments.
- `generate.py` emits mixed streams: true events (multi-reporter), duplicates, noise, stale reports, and **injected misinformation bursts** — each report carries a hidden ground-truth label (`true_incident_id` or `noise`/`misinfo`).
- `official_feed_stub.py` posts corroborating AVL/weather/sensor events for a subset of true events via `POST /feeds/official`.
- Seeded runs → reproducible datasets saved to `data/validation/`.
- **Exit:** one command replays a scenario end-to-end into the running system.
- **Deliverable progress:** **API/integration stub** ✅, **validation dataset** ✅.

### Phase 3 — Role-based dashboard & drill-down
**Goal:** the five role views with explicit states.
- **Triage Queue** (officer): priority-sorted, confidence bar, freshness pill, drill-down **EvidenceDrawer** (contributing reports, sources, verification events, map, "why this score").
- **Situation Map** (decision-maker): MapLibre clusters, verified-only toggle, unlocated tray for MISSING-location incidents.
- **Comms Board** (PIO): VERIFIED-only cards + publish gate.
- **Metrics & Admin** (analyst): placeholder wired in Phase 5.
- Global components: `StateBadge`, `FreshnessPill`, `WhyThisScore`, explicit **empty/missing/stale** cards.
- **Exit:** a coordinator can watch a simulated disruption unfold, drill into any incident, and see *why* it scored as it did.
- **Deliverable progress:** **prototype screens** ✅.

### Phase 4 — Field capture & offline mode
**Goal:** field-ready verification that survives no network.
- **Capture & Verify** PWA view: category chips, severity slider, GPS auto-fill, one-tap CONFIRM/DENY.
- Dexie offline queue + Service Worker app-shell cache + background **sync manager** hitting `POST /sync` (idempotent, capture-time truth).
- Low-bandwidth toggle (text-only, deferred images, polling).
- Verification events flow back into the engine and move incident state.
- **Exit:** disable network → capture + verify → re-enable → items sync as `DELAYED_SYNC`, confidence/state update, audit records capture time.
- **Deliverable progress:** offline/low-bandwidth + field workflow ✅.

### Phase 5 — Metrics, experiment & edge cases
**Goal:** prove it works and prove where it fails.
- `metrics/experiment.py`: run **baseline vs. VeriTransit** on the same labelled dataset; compute **TTVHP**, high-priority **recall**, **precision** of VERIFIED-HP, false-verified rate.
- **Metrics & Admin** view renders baseline / target / measured + trend + weight-tuning + audit log.
- Implement/verify the **five edge cases** (PRD §8) with automated tests: conflicting corroboration, stale/expired, misinformation burst, missing location/time, connectivity loss & late sync.
- `error_analysis.py`: categorise misses (false-verified, missed-HP, late-surfaced) with example incidents.
- **Exit:** `GET /metrics/experiment` returns the full comparison; dashboard shows it; edge-case tests green.
- **Deliverable progress:** **metric dashboard** ✅, measurable experiment + **error analysis** ✅.

### Phase 6 — Validation, limitations & demo
**Goal:** stakeholder validation + packaged demo.
- **Short stakeholder validation** (PRD requires it): scripted walkthrough with 3–5 proxy users each in a role (responder, officer, decision-maker, PIO), using a **task + SUS-style questionnaire**; capture whether they could (a) find the top verified high-priority incident, (b) justify a publish decision from evidence, (c) trust the confidence. Record findings + changes made.
- **Limitations report** (`docs/04-Limitations.md`): synthetic-data caveats, rule-model vs. real misinformation, geo/latency assumptions, bias considerations, and the benefit-vs-risk table (PRD §9).
- **Demo script** (§8 below) + seeded scenario for a repeatable 5-minute live demonstration.
- **Exit:** `README` one-command run; demo rehearsed; all deliverables checked off.

---

## 5. The Measurable Experiment (design in detail)

**Hypothesis:** VeriTransit surfaces verified high-priority reports faster and more precisely than chronological manual triage, without letting misinformation reach VERIFIED.

**Setup:**
- **Dataset:** seeded simulator scenario — e.g. 90-minute simulated storm disruption, ~600 reports across ~15 true incidents (3 high-priority), plus ~40% noise/duplicates and 2 injected misinformation bursts. Ground-truth labels stored alongside.
- **Arms:**
  - **Baseline-A:** FIFO list, no clustering/scoring (proxy for manual reading).
  - **Baseline-B:** "act on all" (everything trusted).
  - **System:** VeriTransit engine + responder verifications injected on the same schedule.
- **Procedure:** replay identical stream into each arm; log when each true HP incident first crosses the "surfaced" bar (top-N and, for System, VERIFIED/CORROBORATING ≥ threshold).

**Metrics & how measured:** per PRD §7 table — median **TTVHP**, HP **recall**, **precision** of VERIFIED-HP, **false-verified** rate. Confidence intervals over ≥ 20 seeds.

**Reporting:** table of **baseline / target / measured**, plus **error analysis** — every false-verified and every missed/late HP incident enumerated with the signal breakdown that caused it, feeding weight-tuning recommendations.

---

## 6. Test Strategy

| Layer | What | Tooling |
|---|---|---|
| **Engine unit** | clustering windows, independence/dedup, each confidence signal, priority, state transitions, freshness decay | pytest, table-driven, seeded |
| **Edge cases** | the five PRD §8 scenarios as explicit tests | pytest fixtures per scenario |
| **API integration** | ingest → cluster → verify → publish gate → audit; idempotent `/sync` | pytest + httpx |
| **Offline** | queue persists across reload; capture-time preserved; conflict handling | vitest + fake IndexedDB; manual network-toggle checklist |
| **Frontend** | state badges render correct explicit states; "why this score" matches API; empty/missing/stale states | vitest + React Testing Library |
| **Experiment repeatability** | same seed → same metrics | pytest golden-file |

**Definition of Done (per slice):** feature works end-to-end in the running app, unit + integration tests green, explicit states handled, audit recorded, and it appears in the demo script.

---

## 7. Deliverables Checklist (brief → artifact)

| Brief deliverable | Artifact | Phase |
|---|---|---|
| Requirements specification | `docs/01-PRD.md` (§4–§9) | 0 |
| Prototype screens | 5 role views in `frontend/src/views` | 3–4 |
| Core algorithm / rules | `backend/engine/*` | 1 |
| API / integration stub | FastAPI routes + `official_feed_stub.py` | 2 |
| Validation dataset | `data/validation/*` (labelled, seeded) | 2 |
| Metric dashboard | Metrics & Admin view + `/metrics/experiment` | 5 |
| Limitations report | `docs/04-Limitations.md` + PRD §9 | 6 |
| Final demonstration | Demo script + seeded scenario + README | 6 |
| Baseline/target/measured/error analysis | `metrics/experiment.py` output + dashboard | 5 |
| Benefits vs. operational/social risks | PRD §9 table (surfaced in UI + limitations) | 6 |

---

## 8. Final Demonstration Script (≈ 5 minutes)

1. **Cold open (state the problem):** 600 reports incoming in a simulated storm — show the raw FIFO baseline (unusable wall of text). *[Baseline-A]*
2. **Switch to VeriTransit Triage Queue:** same stream, now ~15 ranked incidents; top item is a VERIFIED high-priority flood. Open **EvidenceDrawer** → "why this score" (corroboration + responder + official feed).
3. **Field verification, offline:** on the responder PWA, turn off network, CONFIRM a corroborating incident + capture a new one; turn network on → items sync as `DELAYED_SYNC`, the incident flips to VERIFIED, audit shows capture time.
4. **Edge cases live:** trigger the **misinformation burst** (held below VERIFIED, manipulation-flagged) and let a VERIFIED incident go **STALE** (drops from current picture, publish blocked).
5. **Decision & comms:** decision-maker on Situation Map toggles verified-only; PIO publishes the one VERIFIED high-priority incident (gate enforced).
6. **Metrics:** open Metrics & Admin — **baseline vs. measured**: median TTVHP down ≥ 50%, HP recall ≥ 0.90, false-verified ≤ 0.05, with the **error-analysis** table. Close on the **benefits-vs-risks** slide.

---

## 9. Risks to Delivery & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scope creep into a full incident-command system | Miss the core | Non-goals locked (PRD §2.2); vertical slices |
| Confidence weights feel arbitrary | Weak validation | Ship default weights **and** the tuning + error-analysis loop; report sensitivity |
| Offline sync bugs eat data | Breaks a headline feature | Idempotent UUID sync, capture-time truth, persistence tests, network-toggle checklist |
| Simulator too clean → inflated metrics | Not credible | Inject realistic noise/duplication/misinfo; report on ≥ 20 seeds with CIs |
| Map/tiles need network | Offline demo fails | Bundle coarse offline tiles; map degrades to list |
| Over-trust of the number in demo | Contradicts our own thesis | Always pair confidence with uncertainty, source mix, and "why this score" |

---

## 10. Estimated Sequencing

Phases are ordered by dependency, each ending in a demoable increment: **0 → 1 → 2 → 3 → 4 → 5 → 6**. Phases 1–2 (engine + simulator) are the critical path — the dashboard, offline mode, and experiment all build on them. Frontend (Phase 3) can begin against Phase-1 APIs as soon as `GET /incidents` returns scored data. The measurable experiment (Phase 5) is gated on the simulator (Phase 2) and engine (Phase 1) but not on offline mode, so it can run in parallel with Phase 4.

---

## 11. Definition of Success (whole prototype)

The prototype is successful when a non-author can, from a cold `README`:
1. start the system with one command,
2. replay a seeded disruption and watch verified high-priority incidents surface and rank,
3. drill into any incident's evidence and confidence breakdown,
4. capture & verify a report **offline** and see it reconcile correctly,
5. see the **five edge cases** handled explicitly,
6. read the **metric dashboard** showing baseline → target → **measured** result with an **error analysis**, and
7. read the **limitations & benefits-vs-risks** report —

thereby demonstrating an **end-to-end, field-ready verification-and-confidence dashboard**, not a concept deck or an isolated notebook.
```
