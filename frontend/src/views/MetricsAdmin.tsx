import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LiveMetrics } from "../api/types";
import { EmptyState } from "../components/common";

// Analyst view: the measurable experiment (baseline -> target -> measured),
// live operational metrics, and the audit trail.
export function MetricsAdmin() {
  const [live, setLive] = useState<LiveMetrics | null>(null);
  const [exp, setExp] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [running, setRunning] = useState(false);

  async function loadLive() { setLive(await api.liveMetrics()); }
  async function loadAudit() { setAudit((await api.audit()).entries.slice(0, 20)); }

  useEffect(() => { loadLive(); loadAudit(); const t = setInterval(loadLive, 4000); return () => clearInterval(t); }, []);

  async function runExperiment() {
    setRunning(true);
    try { setExp(await api.experiment(20)); } finally { setRunning(false); }
  }

  return (
    <div>
      <h2 className="view-head">Metrics & Admin</h2>
      <p className="view-sub">Live operational metrics, the measurable experiment, and the audit trail.</p>

      {live && (
        <div className="kpis" style={{ marginBottom: 16 }}>
          <Kpi n={live.reports} l="Reports ingested" />
          <Kpi n={live.incidents} l="Incidents" />
          <Kpi n={live.verified} l="Verified" good />
          <Kpi n={live.verified_high_priority} l="Verified high-priority" good />
          <Kpi n={live.manipulation_flagged} l="Manipulation flagged" bad={live.manipulation_flagged > 0} />
          <Kpi n={live.published} l="Published" />
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontWeight: 700 }}>Measurable experiment — baseline vs. VeriTransit (20 seeds)</div>
          <button className="toolbtn" onClick={runExperiment} disabled={running}>
            {running ? "Running…" : "Run experiment"}
          </button>
        </div>
        {!exp ? (
          <div className="small" style={{ marginTop: 10 }}>
            Runs the labelled storm scenario through the engine and both baselines. Primary metric:
            Time-to-Verified-High-Priority (TTVHP).
          </div>
        ) : <ExperimentTable exp={exp} />}
      </div>

      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Audit trail (latest)</div>
        {audit.length === 0 ? <EmptyState title="No actions yet" /> : (
          <table className="data">
            <thead><tr><th>When</th><th>Actor</th><th>Entity</th><th>Change</th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td className="mono small">{new Date(a.created_at).toLocaleTimeString()}</td>
                  <td>{a.actor_id} <span className="small">({a.actor_role})</span></td>
                  <td className="small">{a.entity_type}</td>
                  <td>{a.change}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Kpi({ n, l, good, bad }: { n: number; l: string; good?: boolean; bad?: boolean }) {
  return (
    <div className="card stat">
      <span className={`n ${good ? "metric-good" : bad ? "metric-bad" : ""}`}>{n}</span>
      <span className="l">{l}</span>
    </div>
  );
}

function ExperimentTable({ exp }: { exp: any }) {
  const t = exp.targets, s = exp.system, f = exp.baseline_fifo, a = exp.baseline_act_on_all;
  const rows = [
    {
      metric: "Median TTVHP (s)",
      baseline: `${f.median_time_to_verified_hp_s} (FIFO)`,
      target: `−${t.ttvhp_reduction_pct_vs_fifo}%`,
      measured: `${s.median_time_to_verified_hp_s}  (−${exp.ttvhp_reduction_pct_vs_fifo}%)`,
      ok: exp.ttvhp_reduction_pct_vs_fifo >= t.ttvhp_reduction_pct_vs_fifo,
    },
    {
      metric: "High-priority recall",
      baseline: "—", target: `≥ ${t.hp_recall}`, measured: s.hp_recall,
      ok: s.hp_recall >= t.hp_recall,
    },
    {
      metric: "Precision of verified HP",
      baseline: `${a.verified_hp_precision} (act-on-all)`,
      target: `≥ ${t.verified_hp_precision}`, measured: s.verified_hp_precision,
      ok: s.verified_hp_precision >= t.verified_hp_precision,
    },
    {
      metric: "False-verified rate",
      baseline: `${a.false_verified_rate} (act-on-all)`,
      target: `≤ ${t.false_verified_rate_max}`, measured: s.false_verified_rate,
      ok: s.false_verified_rate <= t.false_verified_rate_max,
    },
    {
      metric: "Misinfo reached verified",
      baseline: "—", target: "0", measured: s.misinfo_reached_verified_rate,
      ok: s.misinfo_reached_verified_rate === 0,
    },
  ];
  return (
    <table className="data" style={{ marginTop: 10 }}>
      <thead><tr><th>Metric</th><th>Baseline</th><th>Target</th><th>Measured</th><th></th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.metric}>
            <td>{r.metric}</td>
            <td className="small mono">{r.baseline}</td>
            <td className="mono">{r.target}</td>
            <td className="mono" style={{ fontWeight: 700 }}>{String(r.measured)}</td>
            <td>{r.ok ? <span className="metric-good">✓ met</span> : <span className="metric-bad">✗ missed</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
