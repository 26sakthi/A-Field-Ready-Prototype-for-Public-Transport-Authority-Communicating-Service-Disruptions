// Offline-first capture queue. Actions are written to localStorage first
// (optimistic), each stamped with a client UUID + capture time, and flushed to
// POST /sync when connectivity returns. Capture time is the truth: a report
// captured offline scores as of when it was captured, not when it synced.
import { api } from "../api/client";

export interface QueuedAction {
  client_uuid: string;
  kind: "report" | "verify";
  payload: any;
  captured_offline_at: string;
  status: "QUEUED" | "SYNCED" | "CONFLICT" | "ERROR";
}

const KEY = "veritransit_offline_queue";

function uuid(): string {
  return (crypto as any).randomUUID
    ? (crypto as any).randomUUID()
    : "u_" + Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export function loadQueue(): QueuedAction[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

function saveQueue(q: QueuedAction[]) {
  localStorage.setItem(KEY, JSON.stringify(q));
}

export function enqueue(kind: "report" | "verify", payload: any): QueuedAction {
  const now = new Date().toISOString();
  const action: QueuedAction = {
    client_uuid: uuid(),
    kind,
    payload: { ...payload, captured_offline_at: now },
    captured_offline_at: now,
    status: "QUEUED",
  };
  const q = loadQueue();
  q.push(action);
  saveQueue(q);
  return action;
}

export function pendingCount(): number {
  return loadQueue().filter((a) => a.status === "QUEUED").length;
}

// Attempt to flush all queued actions. Returns the number synced.
export async function flush(): Promise<number> {
  const q = loadQueue();
  const pending = q.filter((a) => a.status === "QUEUED");
  if (pending.length === 0) return 0;
  const actions = pending.map((a) => ({
    client_uuid: a.client_uuid,
    kind: a.kind,
    payload: a.payload,
  }));
  const res = await api.sync(actions);
  const byId: Record<string, string> = {};
  for (const r of res.results) byId[r.client_uuid] = r.status;
  for (const a of q) {
    const st = byId[a.client_uuid];
    if (st === "applied" || st === "duplicate") a.status = "SYNCED";
    else if (st === "conflict") a.status = "CONFLICT";
    else if (st === "error") a.status = "ERROR";
  }
  saveQueue(q);
  return pending.length;
}

export function clearSynced() {
  saveQueue(loadQueue().filter((a) => a.status !== "SYNCED"));
}

export function isOnline(): boolean {
  return navigator.onLine;
}
