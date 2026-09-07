# Limitations Report & Benefits-vs-Risks
## VeriTransit — Crowd-Report Verification & Confidence Dashboard

| | |
|---|---|
| **Document** | Limitations Report |
| **Version** | 1.0 |
| **Date** | 2026-08-18 |
| **Companion docs** | `01-PRD.md`, `02-System-Architecture.md`, `03-Implementation-Plan.md` |

A verification dashboard that hides its own failure modes would recreate the very
trust problem it is meant to solve. This report states, plainly, what the
prototype does **not** do, where the model can be wrong, and how the technology's
benefits weigh against operational and social risks.

---

## 1. Benefits vs. Operational & Social Risks (the required comparison)

| Dimension | Technology benefit | Operational risk | Social risk | Mitigation in the build |
|---|---|---|---|---|
| **Speed** | Surfaces true events minutes before official feeds; measured **−60% time-to-verified-high-priority** vs. manual triage | Over-trust → dispatching crews to phantom incidents | Premature public alerts cause panic | Graded confidence (never binary); publish gate on `VERIFIED` only |
| **Automation** | Ranks 400+ reports a human cannot cross-check in real time | Automation complacency; de-skilling of duty officers | Opaque, unaccountable decisions on public safety | Human-in-the-loop (engine ranks, people decide); "why this score" drill-down; full audit trail |
| **Crowd openness** | More eyes = faster detection | Spam/noise floods the queue | **Misinformation & coordinated manipulation** | Independence weighting + burst/duplicate detection; manipulation flag; measured **0% misinfo reached VERIFIED** |
| **Confidence scoring** | Consistent, explainable, tunable triage | False precision — a number *feels* certain | Bias against low-reputation / low-connectivity communities | Show uncertainty + source mix; reputation is **behavioural & decaying**, never identity-based |
| **Offline field mode** | Verification where networks fail (exactly where disruptions are worst) | Split-brain / stale local state | — | Explicit `DELAYED_SYNC`; capture-time truth; idempotent sync; conflict surfaced, never silently overwritten |
| **Structured capture** | Fast, machine-rankable reports | Coarse categories miss nuance | Reporter location/identity privacy | Pseudonymous reporters; minimal PII; location captured only as needed |

**Net stance:** every benefit is paired with a failure mode the dashboard makes
*visible*. The product's central commitment is to keep **uncertainty and
provenance first-class**, so speed never silently becomes false certainty.

---

## 2. Model & Algorithm Limitations

1. **Rules, not learned NLP.** Confidence is a transparent weighted rule model, not
   a trained misinformation classifier. This is deliberate (explainable,
   reproducible, no training data needed) but it means:
   - Text understanding is shallow (token Jaccard for duplicates; no semantics).
   - A *sophisticated* misinformation campaign that varies wording and uses many
     aged, reputable-looking accounts could evade the burst/duplicate heuristics.
   - The ML upgrade path exists (a learned scorer behind the same interface) but
     is not built.
2. **Weights are hand-tuned defaults.** The signal weights (responder 0.35,
   corroboration 0.25, official 0.20, …) are reasonable but not learned from real
   outcomes. They ship with a tuning surface and error-analysis loop, not a
   calibration guarantee. Confidence numbers are **relative**, not probabilities.
3. **Clustering is geometric.** Incidents are formed by spatial + temporal +
   category proximity anchored to onset. Consequences:
   - Two genuinely distinct events at the same stop within the window may merge.
   - A long-running event (> window) splits into sequential incidents.
   - Background noise of a compatible category near a real event contaminates the
     cluster (observed in the demo: a real cluster can carry many noise reports).
     Verification and priority are unaffected, but raw report counts look inflated.
4. **Reputation cold-start.** New reporters start at a neutral 0.5. A first-time
   true reporter is under-credited; a fresh malicious account is not pre-penalised.
5. **"Impact" is approximate.** Affected-population impact uses category
   criticality + severity, not real ridership or time-of-day demand data.

---

## 3. Experiment Limitations (how to read the numbers)

The measured results (TTVHP −60%, recall 1.00, precision 1.00, false-verified 0.00,
0% misinfo verified) are strong **but come from a synthetic model**, and must be
read with these caveats:

- **Synthetic data.** The simulator encodes our own assumptions about how reports
  cluster, how much noise there is, and how misinformation looks. Real crowds are
  messier and adversaries adapt. These numbers validate the *mechanism*, not
  real-world performance.
- **The baseline is a model.** "Manual FIFO triage" is analytically modelled
  (read + cross-check at ~25 s/report during a backlog). It is a defensible but
  simplified stand-in for a human operator, not a measured human study.
- **Responder confirmations are scheduled, not real.** The experiment injects a
  responder CONFIRM per true incident on a fixed delay; real responder
  availability, disagreement, and error are not modelled.
- **Recall/precision measure incident identity, not cluster purity.** An incident
  counts as a true positive if it is the primary container for a real event, even
  if noise also clustered into it. This is the operationally meaningful definition,
  but it is a modelling choice.
- **Determinism ≠ generality.** Results are averaged over 20 seeds with the same
  scenario shape. A different disruption profile would give different numbers.

**Error analysis** (`metrics.experiment.error_analysis`) enumerates residual
misses each run — e.g. a true incident with a single located report can stay
under-scored (`true_incident_underscored`), and ~40+ reports per run arrive with
no location and are correctly held out of clustering.

---

## 4. Prototype / Engineering Limitations

- **In-memory store, single process.** No persistence across restart, no
  concurrency scaling. The store interface mirrors a SQLite → Postgres/PostGIS
  swap, but that is not implemented.
- **Simulated auth & roles.** Role is chosen in the UI; there is no real identity
  provider, RBAC enforcement server-side beyond the publish gate, or session
  security.
- **Official feeds are stubbed.** No real GTFS-RT / AVL / weather / IoT
  integration; corroboration events are synthetic.
- **Offline uses localStorage + a basic Service Worker**, not a full IndexedDB /
  Background Sync implementation; the *contract* (idempotent, capture-time truth)
  is real, the storage layer is minimal.
- **Map/charts are inline SVG** (chosen for offline self-containment), so they
  lack real basemaps, zoom/pan, and rich charting.
- **Single language / locale.** English text only; no multilingual crowd handling.

---

## 5. What Would Be Required Before Real Deployment

1. Replace the rule scorer's brittle parts with a **calibrated** model trained on
   real, labelled outcomes; report probabilities, not relative scores.
2. Real feed adapters (GTFS-RT/AVL/weather/IoT) behind the official-feed interface.
3. Durable storage (Postgres + PostGIS), authentication, server-enforced RBAC, and
   a hardened audit store.
4. A **human-factors study** with real duty officers and responders to replace the
   modelled baseline and validate the UI under stress.
5. A **data-protection & privacy review** (reporter PII, location retention,
   lawful basis) and an **equity review** (does reputation/scoring disadvantage any
   community or channel?).
6. An **adversarial red-team** of the misinformation and manipulation defences.

---

## 6. Honest One-Line Summary

VeriTransit demonstrates, end-to-end, that **explainable, human-in-the-loop
verification with graded confidence can surface trustworthy high-priority reports
far faster than manual triage while refusing to auto-trust misinformation** — on
synthetic data, with a transparent rule model, and with every simplification above
stated openly.
