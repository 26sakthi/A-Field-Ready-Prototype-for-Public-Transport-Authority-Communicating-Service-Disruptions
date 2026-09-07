import { useEffect, useState } from "react";
import { api } from "../api/client";
import { enqueue, flush, loadQueue, pendingCount, type QueuedAction } from "../offline/queue";

// Field Responder view: fast, one-handed capture. Works offline -- actions queue
// locally and sync on reconnect (capture time is preserved as the truth).
const CATEGORIES = ["flood", "fire", "breakdown", "crowding", "delay", "safety"];

export function CaptureVerify({ online }: { online: boolean }) {
  const [category, setCategory] = useState("flood");
  const [severity, setSeverity] = useState(4);
  const [text, setText] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>({ lat: 13.0827, lng: 80.2707 });
  const [queue, setQueue] = useState<QueuedAction[]>(loadQueue());
  const [msg, setMsg] = useState("");
  const [forceOffline, setForceOffline] = useState(false);

  const effectiveOnline = online && !forceOffline;

  function refreshQueue() { setQueue(loadQueue()); }

  useEffect(() => {
    if (effectiveOnline && pendingCount() > 0) doSync();
    // eslint-disable-next-line
  }, [effectiveOnline]);

  function useGps() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setCoords({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => setMsg("GPS unavailable — you can still submit with no location.")
    );
  }

  async function submit() {
    const payload: any = {
      reporter_id: "responder_field",
      category, severity_claimed: severity, text,
      lat: coords?.lat ?? null, lng: coords?.lng ?? null,
      named_location: "", channel: "app",
    };
    if (effectiveOnline) {
      try {
        await api.createReport({ ...payload, claimed_time: new Date().toISOString() });
        setMsg("Report submitted.");
      } catch {
        enqueue("report", payload); setMsg("Network failed — queued offline.");
      }
    } else {
      enqueue("report", payload);
      setMsg("Offline — captured locally, will sync on reconnect.");
    }
    setText(""); refreshQueue();
  }

  async function doSync() {
    try {
      const n = await flush();
      if (n) setMsg(`Synced ${n} queued action(s) as DELAYED_SYNC (capture time preserved).`);
      refreshQueue();
    } catch { setMsg("Sync failed — still offline."); }
  }

  const pending = queue.filter((q) => q.status === "QUEUED").length;

  return (
    <div style={{ maxWidth: 480, margin: "0 auto" }}>
      <h2 className="view-head">Field Capture & Verify</h2>
      <p className="view-sub">Minimal fields, GPS auto-fill, offline-first.</p>

      <div className="card" style={{ marginBottom: 12, borderColor: effectiveOnline ? "var(--line)" : "var(--danger)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{effectiveOnline ? "🟢 Online" : "🔴 Offline"} · {pending} queued</span>
          <label className="small">
            <input type="checkbox" checked={forceOffline} onChange={(e) => setForceOffline(e.target.checked)} /> Simulate offline
          </label>
        </div>
        {pending > 0 && effectiveOnline && (
          <button className="toolbtn" style={{ marginTop: 8 }} onClick={doSync}>Sync now</button>
        )}
      </div>

      <div className="field">
        <label>Category</label>
        <div className="chips">
          {CATEGORIES.map((c) => (
            <button key={c} className={`chip ${category === c ? "sel" : ""}`} onClick={() => setCategory(c)}>{c}</button>
          ))}
        </div>
      </div>

      <div className="field">
        <label>Severity: {severity}</label>
        <input type="range" min={1} max={5} value={severity} onChange={(e) => setSeverity(+e.target.value)} />
      </div>

      <div className="field">
        <label>What do you see? (optional)</label>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. water rising on platform 2" />
      </div>

      <div className="field">
        <label>Location</label>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="toolbtn" onClick={useGps}>📍 Use GPS</button>
          <button className="toolbtn" onClick={() => setCoords(null)}>Clear (no location)</button>
          <span className="small">{coords ? `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}` : "— none (will be flagged MISSING)"}</span>
        </div>
      </div>

      <button className="big-btn btn-primary" onClick={submit}>Submit report</button>
      {msg && <div className="small" style={{ marginTop: 10 }}>{msg}</div>}

      {queue.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Local queue</div>
          {queue.slice(-8).reverse().map((q) => (
            <div className="small" key={q.client_uuid} style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{q.kind} · {q.payload.category ?? ""}</span>
              <span className={q.status === "SYNCED" ? "metric-good" : q.status === "QUEUED" ? "" : "metric-bad"}>{q.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
