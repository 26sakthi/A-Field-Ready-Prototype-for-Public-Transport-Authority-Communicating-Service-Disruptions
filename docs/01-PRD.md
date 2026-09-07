# Product Requirements Document (PRD)
## VeriTransit — Crowd-Report Verification & Confidence Dashboard for Service-Disruption Coordination

| | |
|---|---|
| **Document** | Product Requirements Document |
| **Product** | VeriTransit (working name) |
| **Version** | 1.0 |
| **Date** | 2026-08-18 |
| **Status** | Draft for prototype build |
| **Owner** | Product / Coordination Systems |

---

## 1. Deep Problem Analysis

### 1.1 The situation
A public transport authority (bus / metro / rail / ferry) must keep the public and its own operations informed during **service disruptions** — signal failures, floods on the track, a stalled train, a fire at a station, a crowd-crush risk, a bridge closure, severe weather. During a disruption the authority is flooded with **crowd-sourced reports**: passengers tweeting, sending WhatsApp messages, calling the hotline, or using an app to say "Line 2 is flooded at Central."

### 1.2 The core pain (root cause)
> **Decision-makers cannot verify crowd-sourced reports quickly enough.**

Crowd reports are simultaneously the **fastest** source of ground truth (a passenger sees the flood minutes before any sensor) and the **least trustworthy** (rumour, panic, duplication, stale info, and occasionally malicious misinformation). A control-room duty officer facing 400 unverified reports in 20 minutes has three bad options today:

1. **Act on everything** → dispatches responders to phantom incidents, cries wolf to the public, erodes trust.
2. **Act on nothing until officially confirmed** → loses the time advantage crowd reports offer; people are stranded or endangered while the report sits unverified.
3. **Manually triage** → does not scale; a human cannot cross-check 400 reports against each other, against location, against time, and against official feeds in real time.

The consequence is measured in **time-to-verified-decision**. Every minute a *true, high-priority* report sits unverified is a minute of avoidable risk; every minute spent chasing a *false* report is wasted responder capacity.

### 1.3 What the organisation actually needs
Not a prediction model, and not a dashboard that merely *displays* reports. It needs a system that **verifies** and **scores confidence**, then **surfaces the verified, high-priority reports first**, with the **evidence** attached so a human can make an accountable decision fast. It must degrade gracefully in the field (offline / low bandwidth) and it must be **honest about uncertainty** — showing what is missing, what is stale, and what is merely alleged.

### 1.4 Why this is hard (design tensions)
- **Speed vs. certainty** — the value is early warning, but early = unverified. The system must express *graded* confidence, not a binary verified/unverified.
- **Automation vs. accountability** — decisions during disruptions have safety and legal weight. Automation may *rank and recommend* but a human must *decide*; the audit trail matters.
- **Crowd trust vs. crowd manipulation** — the same openness that gives speed invites spam, panic amplification, and deliberate misinformation.
- **Connectivity** — the field responder verifying a flood is often exactly where the network is worst.

### 1.5 Benefit vs. risk framing (must be explicit in the product)
The product itself must **compare technology benefits against operational and social risks** — this is a first-class requirement, not an afterthought (see §9). A verification dashboard that hides its own failure modes would recreate the trust problem it is meant to solve.

---

## 2. Goals & Non-Goals

### 2.1 Goals
1. **Reduce time-to-verified-high-priority-decision.** Surface verified, high-priority reports to the right role faster than manual triage.
2. **Express calibrated confidence**, not binary truth — with the evidence that produced it available on drill-down.
3. **Never hide uncertainty** — explicit states for missing, stale, disputed, and unverified data.
4. **Work in the field** — offline / low-bandwidth capture and review; fast one-handed data entry.
5. **Keep humans accountable** — the system recommends and ranks; responders and officers verify and decide, with a full audit trail.
6. **Be measurable** — ship with a baseline, a target, a measured result, and an error analysis on simulated data.

### 2.2 Non-Goals (for this prototype)
- Not a public-facing passenger app (we simulate the public as report *sources*).
- Not a real ML/NLP misinformation classifier trained on live data — we use transparent, auditable rules + a lightweight scoring model (extensible to ML later).
- Not integrated with a real transit authority's live feeds — we provide **integration stubs** and a **simulator** instead.
- Not a full incident-command / resource-dispatch system — we hand off *verified* incidents; we don't manage the whole response.

---

## 3. Personas & Role-Based Views

| Role | Primary question | Key needs | Default view |
|---|---|---|---|
| **Field Responder** | "Is what I'm looking at what the report says?" | Fast capture, one-tap confirm/deny, works offline, minimal fields, GPS auto-fill | **Capture & Verify** (mobile, offline-first) |
| **Duty Officer / Coordinator** | "Which reports are real and urgent *right now*?" | Ranked queue by priority×confidence, drill-down evidence, assign to responder, freshness at a glance | **Triage Queue** |
| **Control-Room Decision-Maker** | "What's the verified operational picture, and what do we tell the public?" | Map + incident clusters, verified-only toggle, trend of verified high-priority over time, publish gate | **Situation Map + Metrics** |
| **Public Information Officer** | "What is safe and confirmed enough to communicate?" | Verified incidents only, confidence & source count, suggested message, staleness guard | **Comms Board** |
| **Analyst / Admin (support)** | "Is the system itself trustworthy?" | Metric dashboard, error analysis, source-reputation tuning, audit log | **Metrics & Admin** |

Role-based access controls **what is shown, what is actionable, and what is publishable**. A responder can verify but not publish to the public; a PIO can publish but only *verified* incidents; the decision-maker can override with a logged justification.

---

## 4. Core Concepts & Data Model (functional view)

### 4.1 Report
A single crowd-sourced claim. Fields: `id`, `source_channel` (app/SMS/social/hotline/sensor), `reporter_id` (pseudonymous), `text`, `category` (flood, fire, breakdown, crowding, delay, safety, other), `claimed_location` (lat/lng + named stop/line), `claimed_time`, `severity_claimed`, `attachments` (photo hash), `received_at`, `device_offline_captured_at` (for late-synced field entries).

### 4.2 Incident (cluster)
Reports that describe the **same real-world event** are clustered by spatial + temporal + category proximity into an **Incident**, which carries the aggregate confidence, priority, and lifecycle state. This clustering is what turns 400 noisy reports into ~12 decidable incidents.

### 4.3 Verification event
An explicit responder/officer action on a report or incident: `CONFIRM`, `DENY`, `NEEDS_MORE`, with actor role, timestamp, note, and (optional) geotag. This is the strongest confidence signal and the backbone of the audit trail.

### 4.4 Corroborating source
Independent evidence: another citizen report, an **official feed** (vehicle AVL gap, ticket-gate anomaly, weather alert, IoT water sensor), or a responder verification. Independence matters — 50 retweets of one claim are **not** 50 sources.

### 4.5 States (explicit — never implicit "unknown")
**Confidence/verification state (incident):** `UNVERIFIED` → `CORROBORATING` → `VERIFIED` / `DISPUTED` / `DEBUNKED`.
**Freshness state (per report & incident):** `FRESH` (< 5 min) · `RECENT` (5–15 min) · `AGING` (15–45 min) · `STALE` (> staleness threshold, category-dependent) · `EXPIRED` (past its useful life).
**Data-availability state:** `MISSING` (a required signal never arrived, e.g. no GPS), `PARTIAL`, `DELAYED_SYNC` (field-captured offline, synced late), `CONFLICTING`.

These states are surfaced **visually and explicitly** everywhere — a stale VERIFIED incident must look different from a fresh VERIFIED one.

---

## 5. Functional Requirements

Requirements use EARS-style phrasing. **P0** = must for prototype, **P1** = should, **P2** = nice.

### 5.1 Ingestion & simulation
- **FR-1 (P0)** The system shall ingest simulated citizen reports via an ingestion API carrying location, time, source channel, category, and text.
- **FR-2 (P0)** The system shall provide a **report simulator** that generates realistic mixed streams (true events, duplicates, noise, stale reports, and injected misinformation) at controllable rates for experiments.
- **FR-3 (P1)** The system shall accept corroborating **official-feed** events (AVL gap, weather alert, sensor) via an integration **stub**.

### 5.2 Verification & confidence (core algorithm)
- **FR-4 (P0)** When two or more reports fall within the spatial (≤ R meters), temporal (≤ T minutes), and category window, the system shall cluster them into one Incident.
- **FR-5 (P0)** The system shall compute a **confidence score (0–100)** per incident from weighted, **independent** signals: corroboration count, source reputation, responder verification, official-feed match, and recency (see Architecture §Algorithm).
- **FR-6 (P0)** The system shall compute a **priority score** = f(severity, confidence, estimated impact/affected population) and rank the triage queue by it.
- **FR-7 (P0)** When a responder submits a CONFIRM/DENY verification, the system shall update the incident's confidence and state within one refresh cycle and record the event in the audit log.
- **FR-8 (P0)** The system shall down-weight non-independent corroboration (same reporter, identical text, retweet bursts) to resist manipulation.

### 5.3 Dashboard & drill-down
- **FR-9 (P0)** The system shall provide **role-based views** (§3) with role-appropriate data and actions.
- **FR-10 (P0)** Each incident shall support **drill-down to evidence**: contributing reports, sources, verification events, map, and the confidence-score breakdown ("why this score").
- **FR-11 (P0)** Every incident and report shall display a **freshness indicator** and its explicit state (§4.5).
- **FR-12 (P0)** The system shall render **explicit empty/missing/stale states** — never a blank or a silently-old value.
- **FR-13 (P0)** The system shall show a **metric dashboard**: verified high-priority reports surfaced, time-to-verification, precision/recall vs. ground truth, and error breakdown.

### 5.4 Field capture & offline
- **FR-14 (P0)** The system shall provide a **field-friendly capture workflow**: minimal required fields, GPS auto-fill, category chips, severity slider, one-tap confirm/deny — usable one-handed.
- **FR-15 (P0)** The system shall operate in an **offline / low-bandwidth mode**: capture and verification actions queue locally and **sync on reconnect**; the UI clearly marks unsynced/`DELAYED_SYNC` items.
- **FR-16 (P1)** The system shall provide a **low-bandwidth data mode** (text-only, deferred images, delta sync) toggle.

### 5.5 Publishing & accountability
- **FR-17 (P0)** The system shall **gate public messaging** so only `VERIFIED` incidents (or a decision-maker override with logged justification) can be marked publishable.
- **FR-18 (P0)** The system shall maintain an **audit trail** of every state change, verification, and publish action with actor, role, and time.

### 5.6 Edge & failure cases (must be handled — see §8)
- **FR-19 (P0)** The system shall handle and clearly display: (a) **conflicting reports** (some confirm, some deny), (b) **stale/expired** incidents, (c) **coordinated misinformation bursts**, (d) **missing location/time**, and (e) **connectivity loss / late sync**.

---

## 6. Non-Functional Requirements
- **NFR-1** Triage queue refresh ≤ 3 s; confidence recompute on new evidence ≤ 1 s for the affected incident.
- **NFR-2** Offline capture must persist across app restart and never lose a queued report.
- **NFR-3** Confidence scoring must be **explainable** — every score decomposes into named, weighted signals shown on drill-down.
- **NFR-4** Accessibility: colour is never the *only* carrier of state (icons + text labels), touch targets ≥ 44 px for field use.
- **NFR-5** Auditability: no state change without an attributable actor and timestamp.
- **NFR-6** Prototype runs on a single machine (SQLite + local services) and in a browser; deployable later to a small server.

---

## 7. Success Metrics (baseline → target → measured)

**Primary metric:** *Verified high-priority reports surfaced quickly* — operationalised as **Time-to-Verified-High-Priority (TTVHP)**: minutes from a true high-priority event's first report to it being ranked in the officer's top-N as `VERIFIED`/`CORROBORATING` with confidence ≥ threshold.

| Metric | Baseline (manual/FIFO triage) | Target | How measured |
|---|---|---|---|
| Median TTVHP | ~ chronological, no ranking (simulate manual) | **≥ 50% reduction** | Simulator ground truth vs. system surface time |
| High-priority **recall** (true HP incidents surfaced in top-N) | N/A | **≥ 0.90** | vs. simulator labels |
| **Precision** of "VERIFIED high-priority" | N/A (act-on-all ≈ low) | **≥ 0.85** | vs. simulator labels |
| False-verified rate (misinformation reaching VERIFIED) | high under act-on-all | **≤ 0.05** | injected-misinformation track |
| Responder verifications needed per true incident | all/manual | **↓ vs. baseline** | count events / incidents |

Every metric ships with an **error analysis**: where the model over/under-scored, and why (§Validation in Implementation Plan).

---

## 8. Edge & Failure Cases (≥ 3 required; we specify 5)

1. **Conflicting corroboration.** Reports split (3 confirm flood, 2 say "all clear"). → Incident enters `DISPUTED`; confidence capped; officer is prompted for responder verification; UI shows the split explicitly, never an averaged-away single number.
2. **Stale / expired data.** A VERIFIED incident receives no new evidence past its category staleness threshold. → Auto-transitions `STALE` then `EXPIRED`; drops out of "current picture"; publish is blocked with a "re-verify" prompt.
3. **Coordinated misinformation burst.** 60 near-identical reports from few reporters / identical text in 90 s. → Independence down-weighting + reporter-reputation collapse the corroboration credit; incident flagged `possible-manipulation`, held below VERIFIED without responder confirmation.
4. **Missing location or time.** Report arrives with no GPS / no timestamp. → Field shown as explicit `MISSING`; report is retained but excluded from spatial clustering and flagged for enrichment; never silently placed at (0,0).
5. **Connectivity loss & late sync.** Field responder captures/verifies offline for 20 min. → Actions queue locally; on reconnect they sync as `DELAYED_SYNC`, timestamped with capture time (not sync time); confidence recomputes and the officer sees "verified 20 min ago (synced just now)".

---

## 9. Benefits vs. Operational & Social Risks (required comparison)

| Dimension | Technology benefit | Operational risk | Social risk | Mitigation in product |
|---|---|---|---|---|
| **Speed** | Surfaces true events minutes before official feeds | Over-trust → dispatching to phantom incidents | Public panic from premature alerts | Graded confidence + publish gate on VERIFIED only |
| **Automation** | Ranks 400 reports a human can't | De-skilling; automation complacency | Opaque decisions affecting safety | Human-in-the-loop; "why this score" drill-down; audit trail |
| **Crowd openness** | More eyes = faster detection | Spam/noise floods the queue | **Misinformation / manipulation**, targeting | Independence weighting, reputation, manipulation flag |
| **Confidence scoring** | Consistent, explainable triage | False precision (a number feels certain) | Bias against low-reputation/low-connectivity communities | Show uncertainty & source mix; reputation is behaviour-based & decaying, not identity-based |
| **Offline field mode** | Verification where networks fail | Split-brain / stale local state | — | Explicit `DELAYED_SYNC`, capture-time truth, conflict surfacing |
| **Data capture** | Structured, fast | Coarse categories miss nuance | Privacy of reporter location/identity | Pseudonymous reporters; minimal PII; location only as needed |

**Net:** the benefits are real but each is paired with a failure mode the *dashboard itself* must make visible. The product's central design stance: **make uncertainty and provenance first-class**, so speed never silently becomes false certainty.

---

## 10. Deliverables Mapping (traceability to the brief)

| Brief deliverable | Where delivered |
|---|---|
| Requirements specification | This PRD (§4–§9) |
| Prototype screens | Implementation Plan §Screens; built app (5 role views) |
| Core algorithm / rules | Architecture §Confidence & Priority Algorithm |
| API / integration stub | Architecture §API; ingestion + official-feed stub |
| Validation dataset | Simulator-generated labelled dataset (Impl. Plan §Data) |
| Metric dashboard | Metrics & Admin view (FR-13) |
| Limitations report | PRD §9 + Impl. Plan §Limitations |
| Final demonstration | Impl. Plan §Demo script |
| Baseline / target / measured / error analysis | PRD §7 + Impl. Plan §Experiment |

---

## 11. Assumptions & Open Questions
- **Assumptions:** synthetic data only; single-authority scope; pseudonymous reporters; English text; a small responder pool; prototype runs locally.
- **Open questions (flagged, non-blocking):** real feed formats (GTFS-RT? proprietary?); reputation cold-start policy for brand-new reporters; retention/PII policy for a real deployment; localisation for multilingual crowds.

*These are defaults chosen to keep the prototype buildable; each is revisited in the Limitations report before any real deployment.*
