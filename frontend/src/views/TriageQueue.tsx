import { useState } from "react";
import type { IncidentSummary, Role } from "../api/types";
import { ConfidenceBar, EmptyState, FreshnessPill, StateBadge } from "../components/common";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { useIncidents } from "../hooks";

// Duty Officer view: incidents ranked by priority (verified high-priority float up),
// with confidence, freshness, and one-click drill-down to evidence.
export function TriageQueue({ role }: { role: Role }) {
  const { incidents, loading, refresh } = useIncidents({ sort: "priority" });
  const [open, setOpen] = useState<string | null>(null);
  const [hideStale, setHideStale] = useState(false);

  const shown = hideStale
    ? incidents.filter((i) => !["STALE", "EXPIRED"].includes(i.freshness_state))
    : incidents;

  return (
    <div>
      <h2 className="view-head">Triage Queue</h2>
      <p className="view-sub">
        Ranked by priority = severity × confidence × impact. Verified, high-priority incidents rise to the top.
      </p>
      <div style={{ marginBottom: 12 }}>
        <label className="small">
          <input type="checkbox" checked={hideStale} onChange={(e) => setHideStale(e.target.checked)} /> Hide stale / expired
        </label>
      </div>

      {loading ? (
        <EmptyState title="Loading incidents…" />
      ) : shown.length === 0 ? (
        <EmptyState title="No incidents in the queue" hint="Load a scenario from the top bar to simulate a disruption." />
      ) : (
        shown.map((i) => <Row key={i.id} i={i} onOpen={() => setOpen(i.id)} />)
      )}

      {open && (
        <EvidenceDrawer incidentId={open} role={role}
          onClose={() => setOpen(null)} onChanged={refresh} />
      )}
    </div>
  );
}

function Row({ i, onOpen }: { i: IncidentSummary; onOpen: () => void }) {
  const stale = ["STALE", "EXPIRED"].includes(i.freshness_state);
  const hp = i.priority >= 40;
  const prioColor = i.priority >= 60 ? "var(--danger)" : i.priority >= 40 ? "var(--disputed)" : "var(--muted)";
  return (
    <div className={`incident-row clickable ${stale ? "stale" : ""}`} onClick={onOpen}>
      <div className="prio-badge" style={{ color: prioColor }}>{i.priority.toFixed(0)}</div>
      <div className="incident-main">
        <div className="incident-title">
          {i.category} · {i.report_count} report{i.report_count !== 1 ? "s" : ""}
          {hp && <span className="tag-hp">HIGH PRIORITY</span>}
        </div>
        <div className="incident-meta">
          <StateBadge state={i.verification_state} flag={i.manipulation_flag} />{" "}
          <FreshnessPill state={i.freshness_state} at={i.last_evidence_at} />
          {i.center_lat == null && <span className="pill missing">NO LOCATION</span>}
        </div>
      </div>
      <ConfidenceBar value={i.confidence} />
    </div>
  );
}
