import { useCallback, useEffect, useRef, useState } from "react";
import { api, connectWs } from "./api/client";
import type { IncidentSummary } from "./api/types";

// Fetch incidents with the given query and keep them live via WebSocket.
export function useIncidents(params: Record<string, string | boolean>) {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const paramsRef = useRef(params);
  paramsRef.current = params;

  const refresh = useCallback(async () => {
    const res = await api.listIncidents(paramsRef.current);
    setIncidents(res.incidents);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const off = connectWs(() => refresh());
    const t = setInterval(refresh, 5000); // polling fallback (low-bandwidth safe)
    return () => { off(); clearInterval(t); };
  }, [refresh, JSON.stringify(params)]);

  return { incidents, loading, refresh };
}
