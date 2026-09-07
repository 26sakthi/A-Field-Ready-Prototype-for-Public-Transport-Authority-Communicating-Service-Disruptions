import type { Evidence, IncidentSummary, LiveMetrics } from "./types";

const BASE = "/api/v1";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* ignore */ }
    throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status, body });
  }
  return res.json();
}

export const api = {
  async listIncidents(params: Record<string, string | boolean> = {}): Promise<{ count: number; incidents: IncidentSummary[] }> {
    const q = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)])
    ).toString();
    return j(await fetch(`${BASE}/incidents?${q}`));
  },

  async getEvidence(id: string): Promise<Evidence> {
    return j(await fetch(`${BASE}/incidents/${id}/evidence`));
  },

  async verify(id: string, payload: object): Promise<any> {
    return j(await fetch(`${BASE}/incidents/${id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
  },

  async publish(id: string, payload: object): Promise<any> {
    return j(await fetch(`${BASE}/incidents/${id}/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
  },

  async createReport(payload: object): Promise<any> {
    return j(await fetch(`${BASE}/reports`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
  },

  async sync(actions: object[]): Promise<any> {
    return j(await fetch(`${BASE}/sync`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actions }),
    }));
  },

  async liveMetrics(): Promise<LiveMetrics> {
    return j(await fetch(`${BASE}/metrics/live`));
  },

  async experiment(seeds = 20): Promise<any> {
    return j(await fetch(`${BASE}/metrics/experiment?seeds=${seeds}`));
  },

  async replay(seed = 42): Promise<any> {
    return j(await fetch(`${BASE}/admin/replay?seed=${seed}`, { method: "POST" }));
  },

  async reset(): Promise<any> {
    return j(await fetch(`${BASE}/admin/reset`, { method: "POST" }));
  },

  async audit(entityId?: string): Promise<any> {
    const q = entityId ? `?entity_id=${entityId}` : "";
    return j(await fetch(`${BASE}/audit${q}`));
  },
};

// Live updates over WebSocket; caller supplies a callback re-fetch trigger.
export function connectWs(onEvent: (msg: any) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/incidents`;
  function open() {
    if (closed) return;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch { /* ignore */ } };
      ws.onclose = () => { if (!closed) setTimeout(open, 1500); };
      ws.onerror = () => { ws?.close(); };
    } catch { setTimeout(open, 1500); }
  }
  open();
  return () => { closed = true; ws?.close(); };
}
