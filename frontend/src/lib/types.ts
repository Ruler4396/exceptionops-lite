export type CaseStatus =
  | "created"
  | "context_ready"
  | "analyzing"
  | "waiting_review"
  | "completed"
  | "rejected"
  | "needs_more_info"
  | "failed";

export interface RuleHit {
  rule_code: string;
  severity: "low" | "medium" | "high";
  message: string;
  evidence_refs: string[];
  suggested_next_checks: string[];
}

export interface AIResult {
  summary: string;
  anomaly_type: string;
  evidence_used: Array<Record<string, unknown>>;
  possible_causes: string[];
  recommended_action: string[];
  risk_level: "low" | "medium" | "high";
  needs_human_review: boolean;
  review_reason: string;
  created_at?: string;
  raw_response_json?: Record<string, unknown>;
}

export interface CaseDetail {
  base_info: {
    case_id: string;
    case_type: string;
    external_ref: string;
    user_description: string;
    notes?: string;
    status: CaseStatus;
    owner: string;
    queue_bucket: string;
    assigned_at?: string | null;
    due_at?: string | null;
    sla_status: "on_track" | "due_soon" | "overdue" | "closed" | "untracked";
    created_at: string;
    updated_at: string;
  };
  records_snapshot: Record<string, unknown> | null;
  rule_results: {
    normalized_anomaly_type: string;
    risk_level: "low" | "medium" | "high";
    needs_human_review: boolean;
    risk_flags: string[];
    rule_hits: RuleHit[];
  } | null;
  ai_result: AIResult | null;
  review_result: {
    reviewer: string;
    decision: string;
    comment?: string;
    created_at: string;
  } | null;
  audit_logs: Array<{
    event_type: string;
    payload: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface QueueMetrics {
  all_open: number;
  waiting_review: number;
  needs_more_info: number;
  overdue: number;
  high_risk: number;
  completed: number;
}

export interface QueueItem {
  case_id: string;
  case_type: string;
  external_ref: string;
  status: CaseStatus;
  queue_bucket: string;
  risk_level: "low" | "medium" | "high";
  rule_hit_count: number;
  owner: string;
  assigned_at?: string | null;
  due_at?: string | null;
  sla_status: "on_track" | "due_soon" | "overdue" | "closed" | "untracked";
  updated_at: string;
  created_at: string;
  summary: string;
}

export interface CaseQueueResponse {
  metrics: QueueMetrics;
  items: QueueItem[];
}
