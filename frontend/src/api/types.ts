export type VerificationState =
  | "UNVERIFIED" | "CORROBORATING" | "VERIFIED" | "DISPUTED" | "DEBUNKED";
export type FreshnessState = "FRESH" | "RECENT" | "AGING" | "STALE" | "EXPIRED";

export interface IncidentSummary {
  id: string;
  category: string;
  center_lat: number | null;
  center_lng: number | null;
  severity: number;
  confidence: number;
  priority: number;
  verification_state: VerificationState;
  freshness_state: FreshnessState;
  manipulation_flag: boolean;
  publishable: boolean;
  published: boolean;
  independent_sources: number;
  confirms: number;
  denies: number;
  official_match: boolean;
  report_count: number;
  first_reported_at: string;
  last_evidence_at: string;
  breakdown?: Breakdown;
}

export interface Breakdown {
  corroboration: number;
  reputation: number;
  responder: number;
  official: number;
  recency: number;
  total: number;
}

export interface Evidence {
  incident: IncidentSummary;
  reports: ReportOut[];
  verifications: VerificationOut[];
  why_this_score: Breakdown;
  official_match: boolean;
  reporters: { id: string; reputation: number | null }[];
}

export interface ReportOut {
  id: string;
  reporter_id: string;
  category: string;
  text: string;
  lat: number | null;
  lng: number | null;
  named_location: string;
  severity_claimed: number;
  claimed_time: string | null;
  received_at: string;
  location_state: "PRESENT" | "MISSING" | "LOW_ACCURACY";
  time_state: "PRESENT" | "MISSING" | "LOW_ACCURACY";
  sync_state: "SYNCED" | "QUEUED" | "DELAYED_SYNC";
}

export interface VerificationOut {
  id: string;
  actor_id: string;
  actor_role: string;
  action: "CONFIRM" | "DENY" | "NEEDS_MORE";
  note: string;
  created_at: string;
  captured_offline_at: string | null;
}

export interface LiveMetrics {
  reports: number;
  incidents: number;
  verified: number;
  verified_high_priority: number;
  manipulation_flagged: number;
  published: number;
  by_verification_state: Record<string, number>;
  by_freshness_state: Record<string, number>;
}

export type Role = "responder" | "officer" | "decision_maker" | "pio" | "analyst";
