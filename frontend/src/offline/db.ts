// IndexedDB storage adapter for VeriTransit field workflow.
// Provides persistent, structured local storage for:
// 1. Pending actions (offline queue)
// 2. Cached incident snapshots (for offline viewing)
// 3. Draft report state (autosaved during input to prevent loss on reload)

export interface StoredAction {
  client_uuid: string;
  kind: "report" | "verify";
  payload: any;
  captured_offline_at: string;
  status: "QUEUED" | "SYNCED" | "CONFLICT" | "ERROR";
}

export interface CachedIncident {
  id: string;
  category: string;
  verification_state: string;
  freshness_state: string;
  confidence: number;
  priority: number;
  data: any;
  cached_at: string;
}

export interface FieldDraft {
  id: string;
  category: string;
  severity: number;
  text: string;
  coords: { lat: number; lng: number } | null;
  updated_at: string;
}

const DB_NAME = "VeriTransitDB";
const DB_VERSION = 1;

let dbPromise: Promise<IDBDatabase> | null = null;

export function openDatabase(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !("indexedDB" in window)) {
      reject(new Error("IndexedDB is not supported in this environment"));
      return;
    }
    const req = window.indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("pending_actions")) {
        const store = db.createObjectStore("pending_actions", { keyPath: "client_uuid" });
        store.createIndex("status", "status", { unique: false });
        store.createIndex("captured_offline_at", "captured_offline_at", { unique: false });
      }
      if (!db.objectStoreNames.contains("cached_incidents")) {
        const store = db.createObjectStore("cached_incidents", { keyPath: "id" });
        store.createIndex("category", "category", { unique: false });
        store.createIndex("verification_state", "verification_state", { unique: false });
      }
      if (!db.objectStoreNames.contains("offline_drafts")) {
        db.createObjectStore("offline_drafts", { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => {
      dbPromise = null;
      reject(req.error);
    };
  });
  return dbPromise;
}

// --- Action Queue Storage ---

export async function idbSaveAction(action: StoredAction): Promise<void> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_actions", "readwrite");
      const store = tx.objectStore("pending_actions");
      const req = store.put(action);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB saveAction failed:", err);
  }
}

export async function idbGetActions(): Promise<StoredAction[]> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_actions", "readonly");
      const store = tx.objectStore("pending_actions");
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB getActions failed:", err);
    return [];
  }
}

export async function idbUpdateActionStatus(client_uuid: string, status: StoredAction["status"]): Promise<void> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_actions", "readwrite");
      const store = tx.objectStore("pending_actions");
      const getReq = store.get(client_uuid);
      getReq.onsuccess = () => {
        const item = getReq.result;
        if (item) {
          item.status = status;
          store.put(item);
        }
        resolve();
      };
      getReq.onerror = () => reject(getReq.error);
    });
  } catch (err) {
    console.warn("IndexedDB updateStatus failed:", err);
  }
}

export async function idbClearSyncedActions(): Promise<void> {
  try {
    const db = await openDatabase();
    const actions = await idbGetActions();
    const synced = actions.filter((a) => a.status === "SYNCED");
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_actions", "readwrite");
      const store = tx.objectStore("pending_actions");
      for (const a of synced) {
        store.delete(a.client_uuid);
      }
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (err) {
    console.warn("IndexedDB clearSynced failed:", err);
  }
}

// --- Incident Caching ---

export async function idbCacheIncidents(incidents: any[]): Promise<void> {
  try {
    const db = await openDatabase();
    const now = new Date().toISOString();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("cached_incidents", "readwrite");
      const store = tx.objectStore("cached_incidents");
      for (const inc of incidents) {
        store.put({
          id: inc.id,
          category: inc.category,
          verification_state: inc.verification_state,
          freshness_state: inc.freshness_state,
          confidence: inc.confidence,
          priority: inc.priority,
          data: inc,
          cached_at: now,
        });
      }
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (err) {
    console.warn("IndexedDB cacheIncidents failed:", err);
  }
}

export async function idbGetCachedIncidents(): Promise<CachedIncident[]> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("cached_incidents", "readonly");
      const store = tx.objectStore("cached_incidents");
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB getCachedIncidents failed:", err);
    return [];
  }
}

// --- Field Draft Autosave ---

export async function idbSaveDraft(draft: Omit<FieldDraft, "id" | "updated_at">): Promise<void> {
  try {
    const db = await openDatabase();
    const item: FieldDraft = {
      id: "field_draft",
      ...draft,
      updated_at: new Date().toISOString(),
    };
    return new Promise((resolve, reject) => {
      const tx = db.transaction("offline_drafts", "readwrite");
      const store = tx.objectStore("offline_drafts");
      const req = store.put(item);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB saveDraft failed:", err);
  }
}

export async function idbGetDraft(): Promise<FieldDraft | null> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("offline_drafts", "readonly");
      const store = tx.objectStore("offline_drafts");
      const req = store.get("field_draft");
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB getDraft failed:", err);
    return null;
  }
}

export async function idbClearDraft(): Promise<void> {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("offline_drafts", "readwrite");
      const store = tx.objectStore("offline_drafts");
      const req = store.delete("field_draft");
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn("IndexedDB clearDraft failed:", err);
  }
}
