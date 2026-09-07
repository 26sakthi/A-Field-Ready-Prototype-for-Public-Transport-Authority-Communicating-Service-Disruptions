import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Role } from "./api/types";
import { CaptureVerify } from "./views/CaptureVerify";
import { CommsBoard } from "./views/CommsBoard";
import { MetricsAdmin } from "./views/MetricsAdmin";
import { SituationMap } from "./views/SituationMap";
import { TriageQueue } from "./views/TriageQueue";

const ROLES: { id: Role; label: string }[] = [
  { id: "responder", label: "Field Responder" },
  { id: "officer", label: "Duty Officer" },
  { id: "decision_maker", label: "Decision-Maker" },
  { id: "pio", label: "Public Info Officer" },
  { id: "analyst", label: "Analyst / Admin" },
];

export default function App() {
  const [role, setRole] = useState<Role>("officer");
  const [online, setOnline] = useState(navigator.onLine);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  async function replay() {
    setBusy("Loading scenario…");
    try { const r = await api.replay(42); setBusy(`Loaded ${r.reports} reports → ${r.incidents} incidents`); }
    catch { setBusy("Backend unreachable — is it running on :8000?"); }
    setTimeout(() => setBusy(""), 4000);
  }
  async function reset() { await api.reset(); setBusy("Cleared."); setTimeout(() => setBusy(""), 2000); }

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">Veri<span>Transit</span></div>
        <div className="roles">
          {ROLES.map((r) => (
            <button key={r.id} className={`role-btn ${role === r.id ? "active" : ""}`} onClick={() => setRole(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
        <div className="spacer" />
        {busy && <span className="small">{busy}</span>}
        <button className="toolbtn" onClick={replay}>▶ Load storm scenario</button>
        <button className="toolbtn" onClick={reset}>Reset</button>
        <span className={`status-chip ${online ? "status-online" : "status-offline"}`}>
          {online ? "● Online" : "● Offline"}
        </span>
      </div>

      <div className="main">
        {role === "responder" && <CaptureVerify online={online} />}
        {role === "officer" && <TriageQueue role={role} />}
        {role === "decision_maker" && <SituationMap role={role} />}
        {role === "pio" && <CommsBoard role={role} />}
        {role === "analyst" && <MetricsAdmin />}
      </div>
    </div>
  );
}
