// Offline-first capture queue with IndexedDB & localStorage dual-persistence.
// Actions are stored in IndexedDB (primary) & localStorage (fallback),
// stamped with a client UUID + capture time, and flushed to POST /sync.
import { api } from "../api/client";
import {
  idbClearSyncedActions,
  idbGetActions,
  idbSaveAction,
  idbUpdateActionStatus,
  StoredAction,
} from "./db";

export type QueuedAction = StoredAction;

const KEY = "veritransit_offline_queue";

function uuid(): string {
  return (crypto as any).randomUUID
    ? (crypto as any).randomUUID()
    : "u_" + Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export function loadQueue(): QueuedAction[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function saveQueue(q: QueuedAction[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(q));
  } catch (err) {
    console.warn("localStorage save failed:", err);
  }
}

export async function loadQueueAsync(): Promise<QueuedAction[]> {
  const idbActions = await idbGetActions();
  if (idbActions.length > 0) {
    saveQueue(idbActions); // sync to localStorage cache
    return idbActions;
  }
  return loadQueue();
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
  idbSaveAction(action); // Persist to IndexedDB asynchronously
  return action;
}

export async function enqueueAsync(kind: "report" | "verify", payload: any): Promise<QueuedAction> {
  const action = enqueue(kind, payload);
  await idbSaveAction(action);
  return action;
}

export function pendingCount(): number {
  return loadQueue().filter((a) => a.status === "QUEUED").length;
}

export async function pendingCountAsync(): Promise<number> {
  const q = await loadQueueAsync();
  return q.filter((a) => a.status === "QUEUED").length;
}

// Attempt to flush all queued actions. Returns the number synced.
export async function flush(): Promise<number> {
  const q = await loadQueueAsync();
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
    if (st === "applied" || st === "duplicate") {
      a.status = "SYNCED";
    } else if (st === "conflict") {
      a.status = "CONFLICT";
    } else if (st === "error") {
      a.status = "ERROR";
    }
    await idbUpdateActionStatus(a.client_uuid, a.status);
  }
  saveQueue(q);
  return pending.length;
}

export function clearSynced() {
  saveQueue(loadQueue().filter((a) => a.status !== "SYNCED"));
  idbClearSyncedActions();
}

export function isOnline(): boolean {
  return navigator.onLine;
}
