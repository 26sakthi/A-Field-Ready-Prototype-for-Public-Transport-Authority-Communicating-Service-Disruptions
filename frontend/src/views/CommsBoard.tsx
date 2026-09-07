import { useState } from "react";
import { api } from "../api/client";
import type { IncidentSummary, Role } from "../api/types";
import { ConfidenceBar, EmptyState, FreshnessPill, StateBadge } from "../components/common";
import { useIncidents } from "../hooks";

// Public Information Officer view: only VERIFIED, non-stale incidents are
// publishable. The publish gate enforces this; stale items show why they're blocked.
export function CommsBoard({ role }: { role: Role }) {
  const { incidents, loading, refresh } = useIncidents({ role: "pio", sort: "priority" });
  const [msg, setMsg] = useState("");

  async function publish(i: IncidentSummary) {
    setMsg("");
    try {
      await api.publish(i.id, { actor_id: "pio_1", actor_role: role });
      setMsg(`Published ${i.category} incident.`); refresh();
    } catch (e: any) {
      setMsg(`Blocked: ${e.body?.reason ?? "not verified / stale"}`);
    }
  }

  return (
    <div>
      <h2 className="view-head">Comms Board</h2>
      <p className="view-sub">Only VERIFIED, non-stale incidents can be published. Everything here is safe to communicate.</p>
      {msg && <div className="card" style={{ marginBottom: 12 }}>{msg}</div>}

      {loading ? <EmptyState title="Loading…" /> :
        incidents.length === 0 ? (
          <EmptyState title="Nothing verified to communicate yet"
            hint="Incidents appear here once a responder confirms them and they are still fresh." />
        ) : (
          <div className="grid cols-2">
            {incidents.map((i) => (
              <div className="card" key={i.id}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 700, textTransform: "capitalize" }}>{i.category}</span>
                  <FreshnessPill state={i.freshness_state} at={i.last_evidence_at} />
                </div>
                <div style={{ margin: "6px 0" }}><StateBadge state={i.verification_state} /></div>
                <div className="small" style={{ marginBottom: 6 }}>
                  {i.independent_sources} independent sources · {i.confirms} responder confirm(s)
                  {i.official_match && " · official-feed match"}
                </div>
                <ConfidenceBar value={i.confidence} />
                <div style={{ marginTop: 10 }}>
                  <div className="small" style={{ marginBottom: 6, fontStyle: "italic" }}>
                    Suggested: “Confirmed {i.category} affecting service. Crews on site. Updates to follow.”
                  </div>
                  {i.published ? (
                    <span className="badge b-VERIFIED">✓ PUBLISHED</span>
                  ) : (
                    <button className="toolbtn btn-primary" style={{ color: "#04121f", fontWeight: 700 }}
                      disabled={!i.publishable} onClick={() => publish(i)}>
                      📢 Publish {i.publishable ? "" : "(gated)"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}
