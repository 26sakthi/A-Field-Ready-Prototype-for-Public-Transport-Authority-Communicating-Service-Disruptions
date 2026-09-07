import type { Breakdown, FreshnessState, VerificationState } from "../api/types";

export function StateBadge({ state, flag }: { state: VerificationState; flag?: boolean }) {
  const icon: Record<VerificationState, string> = {
    VERIFIED: "✓", CORROBORATING: "◑", UNVERIFIED: "○",
    DISPUTED: "⚠", DEBUNKED: "✕",
  };
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      <span className={`badge b-${state}`}>{icon[state]} {state}</span>
      {flag && <span className="badge b-flag" title="Possible coordinated manipulation">⚑ FLAGGED</span>}
    </span>
  );
}

export function FreshnessPill({ state, at }: { state: FreshnessState; at?: string }) {
  const label = at ? `${state} · ${relTime(at)}` : state;
  return <span className={`fresh ${state}`} title="Freshness of most recent evidence">{label}</span>;
}

export function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 70 ? "var(--verified)" : value >= 45 ? "var(--corroborating)" : "var(--unverified)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div className="confbar"><div style={{ width: `${Math.max(2, value)}%`, background: color }} /></div>
      <span className="mono" style={{ fontSize: 12, minWidth: 30 }}>{value.toFixed(0)}</span>
    </div>
  );
}

// "Why this score" — the explainable breakdown of the confidence number.
export function WhyThisScore({ b }: { b: Breakdown }) {
  const rows: [string, number][] = [
    ["Corroboration (independent sources)", b.corroboration],
    ["Reporter reputation", b.reputation],
    ["Responder verification", b.responder],
    ["Official-feed match", b.official],
    ["Recency", b.recency],
  ];
  const max = Math.max(1, ...rows.map(([, v]) => Math.abs(v)));
  return (
    <div>
      <table className="score-table">
        <tbody>
          {rows.map(([label, v]) => (
            <tr key={label}>
              <td>{label}</td>
              <td style={{ width: 120 }}>
                <div className="score-bar" style={{
                  width: `${(Math.abs(v) / max) * 100}%`,
                  background: v < 0 ? "var(--danger)" : "var(--accent)",
                }} />
              </td>
              <td className="mono">{v >= 0 ? "+" : ""}{v.toFixed(1)}</td>
            </tr>
          ))}
          <tr>
            <td style={{ fontWeight: 700 }}>Total confidence</td>
            <td />
            <td className="mono" style={{ fontWeight: 700 }}>{b.total.toFixed(1)}</td>
          </tr>
        </tbody>
      </table>
      <div className="small">Confidence is a weighted sum of independent signals — no black box.</div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <div style={{ fontSize: 15, marginBottom: 6 }}>{title}</div>
      {hint && <div className="small">{hint}</div>}
    </div>
  );
}

export function relTime(iso: string): string {
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}
