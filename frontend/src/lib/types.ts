// Mirrors backend/app/schemas/{auth,cases}.py. Kept as plain interfaces
// (no codegen) since this is a lean, hand-wired console, not a generated
// client - see PROJECT_PLAN.md Phase 8.

export interface LoginSuccess {
  status: "success";
  access_token: string;
  refresh_token: string;
  user_id: number;
  tenant_id: number | null;
  roles: string[];
}

export interface MfaRequired {
  status: "mfa_required";
  user_id: number;
}

export type LoginResponse = LoginSuccess | MfaRequired;

export interface CaseSummary {
  id: number;
  tier: string;
  state: string;
  assignee_id: number | null;
  sla_due_at: string | null;
  sla_breached: boolean;
  created_at: string;
}

export interface HitResponse {
  id: number;
  entity_uid: number;
  matched_name: string;
  composite_score: number;
  disposition: string;
  disposition_reason: string | null;
  scores: Record<string, unknown>;
}

export interface CaseDetail {
  id: number;
  tenant_id: number;
  application_id: number;
  customer_id: number;
  tier: string;
  state: string;
  assignee_id: number | null;
  decision: string | null;
  decided_by_id: number | null;
  second_approver_id: number | null;
  sla_due_at: string | null;
  sla_breached: boolean;
  hits: HitResponse[];
}

export interface LlmDraftResponse {
  summary: string;
  key_factors: string[];
  suggested_action: string;
  confidence: string;
  source?: string | null;
}

export interface FunnelData {
  submitted: number;
  docs_verified: number;
  screened: number;
  decided: number;
}

export interface RoutingDatum {
  tier: string;
  count: number;
}

export interface ScreeningVolumeDatum {
  date: string;
  count: number;
}

export interface SlaData {
  breached: number;
  on_track: number;
}

export interface LlmUsageData {
  by_provider_status: { provider: string; status: string; calls: number; tokens: number }[];
  cache_hit_rate: number;
  total_calls: number;
}
