import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Evidence, Role } from "../api/types";
import { ConfidenceBar, FreshnessPill, StateBadge, WhyThisScore, relTime } from "./common";

// Drill-down evidence panel: contributing reports, sources, verification events,
// and the confidence breakdown. Officers/responders can act from here.
export function EvidenceDrawer({
  incidentId, role, onClose, onChanged,
}: { incidentId: string; role: Role; onClose: () => void; onChanged: () => void }) {
  const [ev, setEv] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  async function load() {
    setEv(await api.getEvidence(incidentId));
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [incidentId]);

  async function act(action: "CONFIRM" | "DENY") {
    setBusy(true); setMsg("");
    try {
      await api.verify(incidentId, { actor_id: `${role}_1`, actor_role: role, action });
      await load(); onChanged();
    } finally { setBusy(false); }
  }

  async function doPublish() {
    setBusy(true); setMsg("");
    try {
      await api.publish(incidentId, { actor_id: "pio_1", actor_role: role });
      setMsg("Published to public channel."); await load(); onChanged();
    } catch (e: any) {
      setMsg(`Publish blocked: ${e.body?.reason ?? e.body?.detail?.reason ?? "not verified / stale"}`);
    } finally { setBusy(false); }
  }

  if (!ev) return null;
  const i = ev.incident;
  const canVerify = role === "responder" || role === "officer";
  const canPublish = role === "pio" || role === "decision_maker";

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close-x" onClick={onClose}>×</button>
        <h3 style={{ textTransform: "capitalize" }}>
          {i.category} incident {i.published && <span className="pill">PUBLISHED</span>}
        </h3>
        <div style={{ margin: "8px 0" }}>
          <StateBadge state={i.verification_state} flag={i.manipulation_flag} />{" "}
          <FreshnessPill state={i.freshness_state} at={i.last_evidence_at} />
        </div>
        <div style={{ margin: "10px 0" }}>
          <div className="small">Confidence</div>
          <ConfidenceBar value={i.confidence} />
        </div>

        <div className="card" style={{ margin: "12px 0" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Why this score</div>
          <WhyThisScore b={ev.why_this_score} />
        </div>

        <div className="kpis" style={{ marginBottom: 12 }}>
          <div className="stat"><span className="n">{i.independent_sources}</span><span className="l">Independent sources</span></div>
          <div className="stat"><span className="n">{i.confirms}/{i.denies}</span><span className="l">Confirms / denies</span></div>
          <div className="stat"><span className="n">{i.priority.toFixed(0)}</span><span className="l">Priority</span></div>
          <div className="stat"><span className="n">{ev.official_match ? "✓" : "—"}</span><span className="l">Official match</span></div>
        </div>

        {i.manipulation_flag && (
          <div className="card" style={{ borderColor: "var(--danger)", marginBottom: 12 }}>
            ⚑ <b>Possible coordinated manipulation.</b> Corroboration credit collapsed;
            held below VERIFIED until a responder physically confirms.
          </div>
        )}

        <h4>Contributing reports ({ev.reports.length})</h4>
        {ev.reports.slice(0, 30).map((r) => (
          <div className="evi-report" key={r.id}>
            <div>{r.text || <i className="small">(no text)</i>}</div>
            <div className="small">
              {r.reporter_id} · sev {r.severity_claimed} · {relTime(r.received_at)}
              {r.location_state === "MISSING" && <span className="pill missing">NO LOCATION</span>}
              {r.time_state === "MISSING" && <span className="pill missing">NO TIME</span>}
              {r.sync_state === "DELAYED_SYNC" && <span className="pill delayed">SYNCED LATE</span>}
            </div>
          </div>
        ))}

        {ev.verifications.length > 0 && (
          <>
            <h4>Verification events</h4>
            {ev.verifications.map((v) => (
              <div className="evi-report" key={v.id}>
                <b>{v.action}</b> by {v.actor_id} ({v.actor_role}) · {relTime(v.created_at)}
                {v.captured_offline_at && <span className="pill delayed">captured offline</span>}
              </div>
            ))}
          </>
        )}

        <div style={{ position: "sticky", bottom: 0, background: "var(--bg-2)", paddingTop: 12 }}>
          {msg && <div className="small" style={{ marginBottom: 8 }}>{msg}</div>}
          {canVerify && (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="big-btn btn-confirm" disabled={busy} onClick={() => act("CONFIRM")}>✓ Confirm</button>
              <button className="big-btn btn-deny" disabled={busy} onClick={() => act("DENY")}>✕ Deny</button>
            </div>
          )}
          {canPublish && (
            <button className="big-btn btn-primary" disabled={busy} onClick={doPublish}
              title="Only VERIFIED, non-stale incidents publish">
              📢 Publish to public {i.publishable ? "" : "(gated)"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
