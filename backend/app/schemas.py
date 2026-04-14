from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CaseStatus = Literal[
    "created",
    "context_ready",
    "analyzing",
    "waiting_review",
    "completed",
    "rejected",
    "needs_more_info",
    "failed",
]


class CaseCreateRequest(BaseModel):
    anomaly_type: str = Field(min_length=2, max_length=64)
    external_ref: str = Field(min_length=2, max_length=64)
    user_description: str = Field(min_length=8, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)


class CaseCreateResponse(BaseModel):
    case_id: str
    status: CaseStatus


class RuleHit(BaseModel):
    rule_code: str
    severity: Literal["low", "medium", "high"]
    message: str
    evidence_refs: list[str]
    suggested_next_checks: list[str]


class ContextSnapshot(BaseModel):
    case_id: str
    records: dict[str, Any]
    rule_results: dict[str, Any]
    notes: dict[str, Any]
    matched_sop_refs: list[dict[str, str]]


class AIAnalysisResult(BaseModel):
    summary: str
    anomaly_type: str
    evidence_used: list[dict[str, Any]]
    possible_causes: list[str]
    recommended_action: list[str]
    risk_level: Literal["low", "medium", "high"]
    needs_human_review: bool
    review_reason: str
    audit_payload: dict[str, Any]


class AnalyzeCaseResponse(BaseModel):
    run_id: str
    current_status: CaseStatus
    ai_result: AIAnalysisResult


class ReviewDecision(BaseModel):
    reviewer: str = Field(min_length=2, max_length=128)
    decision: Literal["approve", "reject", "request_more_info"]
    comment: str | None = Field(default=None, max_length=1000)


class ReviewResult(BaseModel):
    reviewer: str
    decision: str
    comment: str | None
    created_at: datetime


class AuditLogEntry(BaseModel):
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class CaseDetailResponse(BaseModel):
    base_info: dict[str, Any]
    records_snapshot: dict[str, Any] | None
    rule_results: dict[str, Any] | None
    ai_result: dict[str, Any] | None
    review_result: dict[str, Any] | None
    audit_logs: list[AuditLogEntry]

