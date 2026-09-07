import { useState } from "react";
import type { IncidentSummary, Role } from "../api/types";
import { EmptyState } from "../components/common";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { useIncidents } from "../hooks";

// Decision-Maker view: geographic situation picture (self-contained inline SVG map,
// no external tiles -> works offline). Verified-only toggle; unlocated incidents
// are shown in a separate tray so missing-location data is never hidden.
const BOUNDS = { minLat: 12.97, maxLat: 13.13, minLng: 80.15, maxLng: 80.31 };
const W = 720, H = 460;

function project(lat: number, lng: number) {
  const x = ((lng - BOUNDS.minLng) / (BOUNDS.maxLng - BOUNDS.minLng)) * W;
  const y = H - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * H;
  return { x, y };
}

const stateColor: Record<string, string> = {
  VERIFIED: "#2ec7a0", CORROBORATING: "#3aa0ff", UNVERIFIED: "#7e93a8",
  DISPUTED: "#ffb043", DEBUNKED: "#ff6b6b",
};

export function SituationMap({ role }: { role: Role }) {
  const { incidents, loading, refresh } = useIncidents({ sort: "priority" });
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const located = incidents.filter((i) => i.center_lat != null && i.center_lng != null);
  const unlocated = incidents.filter((i) => i.center_lat == null);
  const shown = verifiedOnly ? located.filter((i) => i.verification_state === "VERIFIED") : located;

  return (
    <div>
      <h2 className="view-head">Situation Map</h2>
      <p className="view-sub">Operational picture. Circle size = priority, colour = verification state.</p>
      <label className="small" style={{ display: "inline-block", marginBottom: 10 }}>
        <input type="checkbox" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} /> Verified only
      </label>

      <div className="grid cols-2">
        <div className="card">
          {loading ? <EmptyState title="Loading…" /> : (
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ background: "#0a1a2b", borderRadius: 8 }}>
              {/* grid */}
              {[...Array(9)].map((_, k) => (
                <line key={`v${k}`} x1={(W / 8) * k} y1={0} x2={(W / 8) * k} y2={H} stroke="#153050" strokeWidth={1} />
              ))}
              {[...Array(7)].map((_, k) => (
                <line key={`h${k}`} x1={0} y1={(H / 6) * k} x2={W} y2={(H / 6) * k} stroke="#153050" strokeWidth={1} />
              ))}
              {shown.map((i) => {
                const { x, y } = project(i.center_lat!, i.center_lng!);
                const r = 6 + (i.priority / 100) * 22;
                return (
                  <g key={i.id} style={{ cursor: "pointer" }} onClick={() => setOpen(i.id)}>
                    <circle cx={x} cy={y} r={r} fill={stateColor[i.verification_state]} fillOpacity={0.35}
                      stroke={stateColor[i.verification_state]} strokeWidth={2} />
                    {i.manipulation_flag && <text x={x} y={y + 4} textAnchor="middle" fontSize={14} fill="#ff6b6b">⚑</text>}
                    {i.verification_state === "VERIFIED" && <text x={x} y={y + 4} textAnchor="middle" fontSize={13} fill="#fff">✓</text>}
                  </g>
                );
              })}
            </svg>
          )}
          <div className="small" style={{ marginTop: 8, display: "flex", gap: 12, flexWrap: "wrap" }}>
            {Object.entries(stateColor).map(([s, c]) => (
              <span key={s}><span style={{ color: c }}>●</span> {s}</span>
            ))}
          </div>
        </div>

        <div>
          <div className="card" style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Unlocated incidents ({unlocated.length})</div>
            <div className="small" style={{ marginBottom: 8 }}>
              Reports arrived with <b>no GPS</b> — retained and flagged for enrichment, never placed at (0,0).
            </div>
            {unlocated.length === 0 ? (
              <div className="small">None — all incidents have a location.</div>
            ) : unlocated.slice(0, 8).map((i) => (
              <div className="incident-row clickable" key={i.id} onClick={() => setOpen(i.id)}>
                <div className="incident-main">
                  <div className="incident-title">{i.category}</div>
                  <div className="incident-meta">{i.verification_state} · {i.report_count} reports</div>
                </div>
                <span className="pill missing">NO LOCATION</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {open && (
        <EvidenceDrawer incidentId={open} role={role} onClose={() => setOpen(null)} onChanged={refresh} />
      )}
    </div>
  );
}
