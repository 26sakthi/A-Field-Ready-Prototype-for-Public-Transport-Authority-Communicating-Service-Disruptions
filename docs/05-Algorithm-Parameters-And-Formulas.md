# 📐 Engine Parameters, Clustering Rules & Scoring Formulas

| | |
|---|---|
| **Document** | Engine Parameters & Formulas Specification |
| **Version** | 1.0 |
| **Date** | 2026-09-29 |
| **Implementation** | [`backend/engine/`](../backend/engine/) (`config.py`, `cluster.py`, `confidence.py`, `independence.py`, `priority.py`, `states.py`, `geo.py`) |

---

## 1. Overview & Architectural Principles

The VeriTransit engine is a **deterministic, rule-based pipeline**. Every confidence score is fully explainable and decomposes into five named components. Every priority score reflects severity, confidence, and line criticality.

This document formalizes all mathematical equations, spatial distance thresholds, temporal decay windows, independence deduplication rules, and state machine transition thresholds.

---

## 2. Spatial & Temporal Clustering

### 2.1 Spatial Distance Threshold (Haversine Radius)
A candidate report $R$ joins an existing open incident $I$ only if the spatial distance between $R$'s coordinates $(\phi_R, \lambda_R)$ and $I$'s centroid $(\phi_I, \lambda_I)$ is within radius $R_{\text{spatial}}$:

$$d_{\text{haversine}}(\phi_1, \lambda_1, \phi_2, \lambda_2) = 2 r_{\text{earth}} \arcsin\left( \sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1) \cos(\phi_2) \sin^2\left(\frac{\Delta \lambda}{2}\right)} \right) \le R_{\text{spatial}}$$

Where:
- $r_{\text{earth}} = 6,371,000\text{ meters}$
- $\Delta \phi = \text{radians}(\phi_2 - \phi_1)$
- $\Delta \lambda = \text{radians}(\lambda_2 - \lambda_1)$
- **Default Spatial Radius ($R_{\text{spatial}}$)**: `250.0 meters` (`EngineConfig.radius_m`)

#### Centroid Recomputation
When a new located report joins incident $I$, the centroid coordinates $(\phi_I, \lambda_I)$ are updated as the arithmetic mean of all located reports attached to $I$:

$$\phi_I = \frac{1}{N_{\text{located}}} \sum_{k=1}^{N_{\text{located}}} \phi_k, \quad \lambda_I = \frac{1}{N_{\text{located}}} \sum_{k=1}^{N_{\text{located}}} \lambda_k$$

### 2.2 Temporal Window
A report $R$ with timestamp $t_{\text{ref}} = \text{claimed\_time} \lor \text{received\_at}$ joins incident $I$ only if:

$$| t_{\text{ref}} - t_{\text{first\_reported}} | \le T_{\text{window}}$$

- **Default Temporal Window ($T_{\text{window}}$)**: `15.0 minutes` (`EngineConfig.time_window_min`)
- **Anchor Principle**: The temporal window is anchored to the incident's **onset** ($t_{\text{first\_reported}}$), rather than its last evidence. This prevents a steady trickle of reports from rolling the window forward indefinitely and absorbing unrelated traffic ("over-clustering").

### 2.3 Category Compatibility Matrix
Reports only cluster into incidents with compatible categories. The compatibility set $\text{COMPATIBLE}(C_A)$ is defined as:

$$\text{COMPATIBLE}(C_A) = \begin{cases} \{\text{FLOOD}\}, & C_A = \text{FLOOD} \\ \{\text{FIRE}\}, & C_A = \text{FIRE} \\ \{\text{BREAKDOWN}\}, & C_A = \text{BREAKDOWN} \\ \{\text{SAFETY}\}, & C_A = \text{SAFETY} \\ \{\text{CROWDING}\}, & C_A = \text{CROWDING} \\ \{\text{DELAY}\}, & C_A = \text{DELAY} \\ \{\text{OTHER}\}, & C_A = \text{OTHER} \end{cases}$$

### 2.4 Missing Location / Time Handling
- Reports with `location_state == MISSING` bypass spatial distance evaluation entirely. They do not seed spatial centroids or join spatial clusters. Instead, they attach to matching category incidents as unlocated evidence and are flagged for enrichment.

---

## 3. Independence, Deduplication & Anti-Manipulation

### 3.1 Text Similarity (Token Jaccard Index)
Let $T(A)$ and $T(B)$ be lowercase token sets (split on whitespace) for report texts $A$ and $B$:

$$J(A, B) = \frac{|T(A) \cap T(B)|}{|T(A) \cup T(B)|}$$

- **Near-Duplicate Threshold ($J_{\text{dup}}$)**: `0.90` (`EngineConfig.dup_jaccard`)

### 3.2 Effective Independent Source Counting
To prevent inflation from retweets, copy-paste campaigns, or multiple submissions from the same user:

1. **Per-Reporter Deduplication**: Group reports by `reporter_id`. Retain only the earliest report per reporter as representative.
2. **Text Collapsing**: Iterate through representative reports. If a report $R_i$ has text similarity $J(R_i, R_j) \ge J_{\text{dup}}$ with an already accepted effective source $R_j$, $R_i$ is collapsed into $R_j$.
3. **Independent Count ($n_{\text{independent}}$)**: The number of distinct uncollapsed effective sources.

### 3.3 Coordinated Burst Detection
A cluster is flagged for potential manipulation (`manipulation_flag = True`) if a group $G$ of reports sharing near-duplicate text ($J \ge J_{\text{dup}}$) satisfies:

$$\text{count}(G) \ge N_{\text{burst}} \quad \text{AND} \quad |\text{reporters}(G)| \le M_{\text{burst}} \quad \text{AND} \quad (t_{\text{max}} - t_{\text{min}}) \le W_{\text{burst}}$$

- **Burst Count Threshold ($N_{\text{burst}}$)**: `8` reports (`EngineConfig.burst_count`)
- **Burst Distinct Reporters ($M_{\text{burst}}$)**: `3` reporters (`EngineConfig.burst_distinct_reporters`)
- **Burst Time Window ($W_{\text{burst}}$)**: `2.0 minutes` (`EngineConfig.burst_window_min`)

#### Manipulation Penalty
If `manipulation_flag == True`, the raw corroboration signal is penalized by multiplying by $\kappa_{\text{manip}} = 0.20$:

$$S_{\text{corr}} \leftarrow \kappa_{\text{manip}} \cdot S_{\text{corr}} = 0.20 \cdot S_{\text{corr}}$$

---

## 4. Explainable Confidence Scoring Formula

The aggregate confidence score $C \in [0.0, 100.0]$ is computed as:

$$C = 100 \times \text{clamp}\left( w_c S_{\text{corr}} + w_r S_{\text{rep}} + w_v S_{\text{resp}} + w_o S_{\text{off}} + w_t S_{\text{rec}}, 0.0, 1.0 \right)$$

### 4.1 Component Weights ($\sum w_i = 1.00$)
| Component | Weight Variable | Default Value | Description |
|---|---|---|---|
| **Corroboration** | $w_c$ | `0.25` | Independent crowd sources |
| **Reporter Reputation** | $w_r$ | `0.10` | Historical reliability of source reporters |
| **Responder Action** | $w_v$ | `0.35` | Field responder CONFIRM / DENY signal |
| **Official Feed Match** | $w_o$ | `0.20` | Match against AVL, weather, or IoT sensor feed |
| **Recency Decay** | $w_t$ | `0.10` | Time decay since last evidence |

### 4.2 Individual Signal Equations

#### 1. Corroboration Signal ($S_{\text{corr}}$)
Uses diminishing returns (logarithmic scaling) capped at $C_{\text{cap}} = 6$:

$$S_{\text{corr}} = \text{clamp}\left( \frac{\log_2(1 + n_{\text{independent}})}{\log_2(1 + C_{\text{cap}})}, 0.0, 1.0 \right)$$

Where $C_{\text{cap}} = 6$ (`EngineConfig.corroboration_cap`).

#### 2. Reputation Signal ($S_{\text{rep}}$)
Mean reputation across reporters of independent effective sources:

$$S_{\text{rep}} = \begin{cases} R_{\text{new}}, & \text{if } |\text{reporters}| = 0 \\ \text{clamp}\left( \frac{1}{K} \sum_{k=1}^K r_k, 0.0, 1.0 \right), & \text{otherwise} \end{cases}$$

- $R_{\text{new}} = 0.50$ (`EngineConfig.new_reporter_reputation`)

#### 3. Responder Signal ($S_{\text{resp}}$)
Net responder confirmations vs. denials:

$$S_{\text{resp}} = \begin{cases} 0.0, & \text{if } N_{\text{confirm}} = 0 \text{ and } N_{\text{deny}} = 0 \\ \text{clamp}\left( N_{\text{confirm}} - N_{\text{deny}}, -1.0, 1.0 \right), & \text{otherwise} \end{cases}$$

#### 4. Official Feed Signal ($S_{\text{off}}$)
Binary match against official feeds within $1.5 \times R_{\text{spatial}} = 375\text{ meters}$:

$$S_{\text{off}} = \begin{cases} 1.0, & \text{if spatial dist} \le 1.5 R_{\text{spatial}} \text{ and category matches} \\ 0.0, & \text{otherwise} \end{cases}$$

#### 5. Recency Signal ($S_{\text{rec}}$)
Exponential decay based on elapsed minutes $\Delta t = (t_{\text{now}} - t_{\text{last\_evidence}}) / 60$:

$$S_{\text{rec}} = \text{clamp}\left( \exp\left( -\frac{\max(0, \Delta t)}{\tau_{\text{category}}} \right), 0.0, 1.0 \right)$$

---

## 5. Temporal Decay Windows ($\tau$) & Freshness States

### 5.1 Category Decay Constants ($\tau_{\text{category}}$)
The decay constant $\tau$ (in minutes) reflects how long an incident of a given type remains actionable:

| Incident Category | Decay Constant $\tau$ (minutes) |
|---|---|
| **FLOOD** | `90.0` |
| **FIRE** | `60.0` |
| **SAFETY** | `60.0` |
| **BREAKDOWN** | `45.0` |
| **OTHER** | `40.0` |
| **DELAY** | `30.0` |
| **CROWDING** | `20.0` |

### 5.2 Freshness State Machine Transitions
Elapsed time $\Delta t$ since $t_{\text{last\_evidence}}$ dictates parallel freshness state:

$$\text{FreshnessState}(\Delta t, \tau) = \begin{cases} 
\text{FRESH}, & \Delta t < 5.0\text{ min} \\
\text{RECENT}, & 5.0\text{ min} \le \Delta t < 15.0\text{ min} \\
\text{AGING}, & 15.0\text{ min} \le \Delta t < 45.0\text{ min} \\
\text{STALE}, & 45.0\text{ min} \le \Delta t < k_{\text{expire}} \cdot \tau \quad (k_{\text{stale}} = 1.5) \\
\text{EXPIRED}, & \Delta t \ge k_{\text{expire}} \cdot \tau \quad (k_{\text{expire}} = 3.0)
\end{cases}$$

- **Stale Factor ($k_{\text{stale}}$)**: `1.5`
- **Expire Factor ($k_{\text{expire}}$)**: `3.0`

---

## 6. Priority Scoring Formula & Category Criticality

The priority score $P \in [0.0, 100.0]$ determines triage queue ordering:

$$P = \text{round}\left( 100 \times S_{\text{norm}} \times C_{\text{norm}} \times I_{\text{norm}}, 1 \right)$$

Where:
- $S_{\text{norm}} = \frac{\text{clamp}(\text{severity}, 1, 5)}{5.0}$
- $C_{\text{norm}} = \frac{\text{confidence}}{100.0}$
- $I_{\text{norm}} = 0.5 \cdot \text{criticality}(C_{\text{incident}}) + 0.5 \cdot S_{\text{norm}}$

### Category Criticality Table
| Category | Criticality Weight |
|---|---|
| **FLOOD** | `1.00` |
| **FIRE** | `1.00` |
| **SAFETY** | `0.95` |
| **CROWDING** | `0.75` |
| **BREAKDOWN** | `0.70` |
| **DELAY** | `0.50` |
| **OTHER** | `0.40` |

---

## 7. Verification State Machine Rules

The verification state $V \in \{\text{UNVERIFIED}, \text{CORROBORATING}, \text{VERIFIED}, \text{DISPUTED}, \text{DEBUNKED}\}$ transitions according to:

1. **DEBUNKED**: $N_{\text{deny}} > 0 \text{ AND } N_{\text{confirm}} == 0$ (Responder DENY dominates).
2. **DISPUTED**: $N_{\text{confirm}} > 0 \text{ AND } N_{\text{deny}} > 0$.
3. **VERIFIED**:
   - $N_{\text{confirm}} > 0$, OR
   - $S_{\text{off}} == 1.0 \text{ AND } C \ge C_{\text{high}} (70.0) \text{ AND } \text{manipulation\_flag} == \text{False}$.
4. **CORROBORATING**: $n_{\text{independent}} \ge N_{\text{min\_corr}} (2)$ and not yet VERIFIED.
5. **UNVERIFIED**: Otherwise.

### Publish Gate Rule
An incident is publishable ($I_{\text{publishable}} == \text{True}$) **if and only if**:
$$V == \text{VERIFIED} \quad \text{AND} \quad \text{FreshnessState} \in \{\text{FRESH}, \text{RECENT}, \text{AGING}\}$$

---

## 8. Summary Table of Engine Configuration Knobs

| Knob / Parameter | Config Field | Default Value | Code Location |
|---|---|---|---|
| Spatial Radius | `radius_m` | `250.0 m` | `backend/engine/config.py` |
| Temporal Window | `time_window_min` | `15.0 min` | `backend/engine/config.py` |
| Jaccard Duplicate Threshold | `dup_jaccard` | `0.90` | `backend/engine/config.py` |
| Burst Count | `burst_count` | `8 reports` | `backend/engine/config.py` |
| Burst Time Span | `burst_window_min` | `2.0 min` | `backend/engine/config.py` |
| Burst Max Reporters | `burst_distinct_reporters` | `3 reporters` | `backend/engine/config.py` |
| Corroboration Weight | `w_corroboration` | `0.25` | `backend/engine/config.py` |
| Reputation Weight | `w_reputation` | `0.10` | `backend/engine/config.py` |
| Responder Weight | `w_responder` | `0.35` | `backend/engine/config.py` |
| Official Feed Weight | `w_official` | `0.20` | `backend/engine/config.py` |
| Recency Weight | `w_recency` | `0.10` | `backend/engine/config.py` |
| Corroboration Cap | `corroboration_cap` | `6 sources` | `backend/engine/config.py` |
| Auto-Verify Confidence | `confidence_high` | `70.0` | `backend/engine/config.py` |
| Min Corroborating Sources | `min_sources_corroborating` | `2 sources` | `backend/engine/config.py` |
