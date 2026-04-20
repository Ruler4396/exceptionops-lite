from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db, init_db
from .dify import analyze_with_dify_or_fallback, build_local_analysis
from .models import Case, CaseAIResult, CaseAuditLog, CaseContextSnapshot, CaseReview
from .rules import evaluate_rules
from .schemas import (
    AnalyzeCaseResponse,
    AssignmentUpdate,
    AuditLogEntry,
    CaseCreateRequest,
    CaseCreateResponse,
    CaseDetailResponse,
    ContextSnapshot,
    ReviewDecision,
)
from .seed_loader import get_record_bundle, iter_record_bundles, match_sops


DEMO_REVIEWERS = [
    "ops.lead@example.com",
    "finance.reviewer@example.com",
    "procurement.pm@example.com",
]

TEAM_OWNERS = [
    "运营处理组",
    "财务支持组",
    "采购运营组",
    "供应链复核组",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        _seed_demo_cases(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _make_case_id() -> str:
    return f"EXO-{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def _log_event(db: Session, case_id: str, event_type: str, payload: dict[str, Any]) -> None:
    db.add(CaseAuditLog(case_id=case_id, event_type=event_type, payload_json=payload))


def _demo_owner(external_ref: str) -> str:
    suffix = external_ref.split("-")[-1]
    try:
        index = int(suffix)
    except ValueError:
        index = (sum(ord(char) for char in external_ref) % len(TEAM_OWNERS)) + 1
    return TEAM_OWNERS[(index - 1) % len(TEAM_OWNERS)]


def _default_owner(case_type: str, external_ref: str) -> str:
    owner_mapping = {
        "amount_mismatch": "财务支持组",
        "quantity_mismatch": "采购运营组",
        "status_conflict": "供应链复核组",
        "field_missing": "运营处理组",
        "stale_exception": "运营处理组",
    }
    return owner_mapping.get(case_type, _demo_owner(external_ref))


def _queue_bucket(status: str) -> str:
    mapping = {
        "waiting_review": "waiting_review",
        "needs_more_info": "needs_more_info",
        "rejected": "rejected",
        "completed": "completed",
        "failed": "failed",
        "created": "new",
        "context_ready": "new",
        "analyzing": "new",
    }
    return mapping.get(status, "new")


def _risk_level_for_case(case: Case, context: CaseContextSnapshot | None, ai_row: CaseAIResult | None) -> str:
    if ai_row is not None:
        return ai_row.risk_level
    if context is not None:
        return context.rule_results_json.get("risk_level", "low")
    return "low"


def _sla_hours(status: str, risk_level: str) -> int | None:
    if status in {"completed", "rejected", "failed"}:
        return None
    mapping = {
        "waiting_review": {"high": 4, "medium": 8, "low": 16},
        "needs_more_info": {"high": 8, "medium": 16, "low": 24},
        "created": {"high": 6, "medium": 12, "low": 24},
        "context_ready": {"high": 6, "medium": 12, "low": 24},
        "analyzing": {"high": 2, "medium": 4, "low": 8},
    }
    default_bucket = mapping["created"]
    return mapping.get(status, default_bucket).get(risk_level, 24)


def _apply_sla(case: Case, risk_level: str, base_time: datetime | None = None) -> None:
    hours = _sla_hours(case.status, risk_level)
    if hours is None:
        case.due_at = None
        return
    reference = base_time or datetime.utcnow()
    case.due_at = reference + timedelta(hours=hours)
    if case.assigned_at is None:
        case.assigned_at = reference


def _sla_status(case: Case) -> str:
    if case.status in {"completed", "rejected", "failed"}:
        return "closed"
    if case.due_at is None:
        return "untracked"
    remaining = case.due_at - datetime.utcnow()
    if remaining.total_seconds() < 0:
        return "overdue"
    if remaining <= timedelta(hours=2):
        return "due_soon"
    return "on_track"


def _latest_context(db: Session, case_id: str) -> CaseContextSnapshot | None:
    return db.scalar(
        select(CaseContextSnapshot)
        .where(CaseContextSnapshot.case_id == case_id)
        .order_by(desc(CaseContextSnapshot.created_at))
        .limit(1)
    )


def _latest_ai_result(db: Session, case_id: str) -> CaseAIResult | None:
    return db.scalar(
        select(CaseAIResult)
        .where(CaseAIResult.case_id == case_id)
        .order_by(desc(CaseAIResult.created_at))
        .limit(1)
    )


def _latest_review(db: Session, case_id: str) -> CaseReview | None:
    return db.scalar(
        select(CaseReview)
        .where(CaseReview.case_id == case_id)
        .order_by(desc(CaseReview.created_at))
        .limit(1)
    )


def _case_or_404(db: Session, case_id: str) -> Case:
    case = db.scalar(select(Case).where(Case.case_id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


def _build_context_snapshot(db: Session, case: Case, refresh: bool = False) -> ContextSnapshot:
    existing = _latest_context(db, case.case_id)
    if existing and not refresh:
        return ContextSnapshot(
            case_id=case.case_id,
            records=existing.records_json,
            rule_results=existing.rule_results_json,
            notes=existing.notes_json,
            matched_sop_refs=existing.notes_json.get("matched_sop_refs", []),
        )

    bundle = get_record_bundle(case.external_ref)
    if bundle is None:
        case.status = "failed"
        _log_event(
            db,
            case.case_id,
            "context_failed",
            {"reason": "external_ref_not_found", "external_ref": case.external_ref},
        )
        db.commit()
        raise HTTPException(status_code=404, detail="No mock record bundle found for this external_ref.")

    rule_results = evaluate_rules(bundle)
    sop_refs = match_sops([hit["rule_code"] for hit in rule_results["rule_hits"]])
    notes_json = {
        "manual_notes": bundle.get("manual_notes", []),
        "similar_case_summaries": bundle.get("similar_case_summaries", []),
        "sop_hint": bundle.get("sop_hint", ""),
        "matched_sop_refs": sop_refs,
    }
    snapshot = CaseContextSnapshot(
        case_id=case.case_id,
        records_json=bundle["records"],
        rule_results_json=rule_results,
        notes_json=notes_json,
    )
    db.add(snapshot)
    case.status = "context_ready"
    _log_event(
        db,
        case.case_id,
        "context_ready",
        {
            "rule_codes": [hit["rule_code"] for hit in rule_results["rule_hits"]],
            "risk_level": rule_results["risk_level"],
        },
    )
    db.commit()
    db.refresh(snapshot)
    return ContextSnapshot(
        case_id=case.case_id,
        records=snapshot.records_json,
        rule_results=snapshot.rule_results_json,
        notes=snapshot.notes_json,
        matched_sop_refs=sop_refs,
    )


def _to_ai_result_payload(ai_row: CaseAIResult | None) -> dict[str, Any] | None:
    if ai_row is None:
        return None
    return {
        "summary": ai_row.summary,
        "anomaly_type": ai_row.anomaly_type,
        "evidence_used": ai_row.evidence_json,
        "possible_causes": ai_row.causes_json,
        "recommended_action": ai_row.recommendation_json,
        "risk_level": ai_row.risk_level,
        "needs_human_review": ai_row.needs_human_review,
        "review_reason": ai_row.review_reason,
        "raw_response_json": ai_row.raw_response_json,
        "created_at": ai_row.created_at,
    }


def _sync_local_analysis(case: Case, context: ContextSnapshot) -> tuple[str, dict[str, Any]]:
    payload = {
        "case_id": case.case_id,
        "external_ref": case.external_ref,
        "anomaly_type": case.case_type,
        "user_description": case.user_description,
        "records": context.records,
        "rule_results": context.rule_results,
        "notes": context.notes,
        "matched_sop_refs": context.matched_sop_refs,
    }
    return f"seed-{case.case_id.lower()}", build_local_analysis(payload)


def _store_ai_result(db: Session, case: Case, run_id: str, ai_result: dict[str, Any]) -> CaseAIResult:
    ai_row = CaseAIResult(
        case_id=case.case_id,
        dify_run_id=run_id,
        summary=ai_result["summary"],
        anomaly_type=ai_result["anomaly_type"],
        evidence_json=ai_result["evidence_used"],
        causes_json=ai_result["possible_causes"],
        recommendation_json=ai_result["recommended_action"],
        risk_level=ai_result["risk_level"],
        needs_human_review=ai_result["needs_human_review"],
        review_reason=ai_result["review_reason"],
        raw_response_json=ai_result,
    )
    db.add(ai_row)
    return ai_row


def _seed_demo_cases(db: Session) -> None:
    db.execute(delete(CaseAuditLog).where(CaseAuditLog.case_id.like("DEMO-%")))
    db.execute(delete(CaseReview).where(CaseReview.case_id.like("DEMO-%")))
    db.execute(delete(CaseAIResult).where(CaseAIResult.case_id.like("DEMO-%")))
    db.execute(delete(CaseContextSnapshot).where(CaseContextSnapshot.case_id.like("DEMO-%")))
    db.execute(delete(Case).where(Case.case_id.like("DEMO-%")))
    db.commit()

    bundles = iter_record_bundles()
    for index, bundle in enumerate(bundles, start=1):
        suffix = bundle["external_ref"].split("-")[-1]
        case = Case(
            case_id=f"DEMO-{suffix}",
            case_type=bundle.get("default_anomaly_type", "cross_system_exception"),
            external_ref=bundle["external_ref"],
            user_description=bundle.get("sop_hint") or bundle.get("manual_notes", [""])[0],
            notes=(bundle.get("manual_notes") or [None])[0],
            owner=_default_owner(bundle.get("default_anomaly_type", "cross_system_exception"), bundle["external_ref"]),
            assigned_at=datetime.utcnow(),
            status="created",
        )
        db.add(case)
        _log_event(
            db,
            case.case_id,
            "case_seeded",
            {
                "external_ref": case.external_ref,
                "owner": _demo_owner(case.external_ref),
            },
        )
        db.flush()

        context = _build_context_snapshot(db, case, refresh=True)
        run_id, ai_result = _sync_local_analysis(case, context)
        _store_ai_result(db, case, run_id, ai_result)

        rule_results = context.rule_results
        needs_review = ai_result["needs_human_review"]
        has_stale = "stale_exception" in rule_results["risk_flags"]
        if needs_review:
            if index % 4 == 1:
                case.status = "waiting_review"
            elif index % 4 == 2:
                case.status = "needs_more_info"
                review = CaseReview(
                    case_id=case.case_id,
                    reviewer=DEMO_REVIEWERS[index % len(DEMO_REVIEWERS)],
                    decision="request_more_info",
                    comment="关键证据不足，需先补齐源字段后再关闭案例。",
                )
                db.add(review)
                _log_event(
                    db,
                    case.case_id,
                    "review_recorded",
                    {"decision": "request_more_info", "reviewer": review.reviewer},
                )
            elif index % 4 == 3 and not has_stale:
                case.status = "completed"
                review = CaseReview(
                    case_id=case.case_id,
                    reviewer=DEMO_REVIEWERS[index % len(DEMO_REVIEWERS)],
                    decision="approve",
                    comment="按受控人工处置路径通过，保留审计留痕。",
                )
                db.add(review)
                _log_event(
                    db,
                    case.case_id,
                    "review_recorded",
                    {"decision": "approve", "reviewer": review.reviewer},
                )
            else:
                case.status = "rejected"
                review = CaseReview(
                    case_id=case.case_id,
                    reviewer=DEMO_REVIEWERS[index % len(DEMO_REVIEWERS)],
                    decision="reject",
                    comment="驳回，等待上游责任方修正后重新流转。",
                )
                db.add(review)
                _log_event(
                    db,
                    case.case_id,
                    "review_recorded",
                    {"decision": "reject", "reviewer": review.reviewer},
                )
        else:
            case.status = "completed"

        _apply_sla(case, ai_result["risk_level"])
        if case.status in {"waiting_review", "needs_more_info"} and (has_stale or index % 5 == 0) and case.due_at is not None:
            case.due_at = datetime.utcnow() - timedelta(hours=3)

        _log_event(
            db,
            case.case_id,
            "analysis_completed",
            {
                "run_id": run_id,
                "risk_level": ai_result["risk_level"],
                "needs_human_review": ai_result["needs_human_review"],
            },
        )

    db.commit()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "service": settings.app_name,
        "ok": True,
        "timestamp": _utc_iso(),
        "dify_enabled": settings.dify_enabled,
    }


@app.post("/api/cases", response_model=CaseCreateResponse)
def create_case(payload: CaseCreateRequest, db: Session = Depends(get_db)) -> CaseCreateResponse:
    case = Case(
        case_id=_make_case_id(),
        case_type=payload.anomaly_type,
        external_ref=payload.external_ref,
        user_description=payload.user_description,
        notes=payload.notes,
        owner=_default_owner(payload.anomaly_type, payload.external_ref),
        assigned_at=datetime.utcnow(),
        status="created",
    )
    _apply_sla(case, "medium", base_time=datetime.utcnow())
    db.add(case)
    _log_event(
        db,
        case.case_id,
        "case_created",
        {
            "anomaly_type": payload.anomaly_type,
            "external_ref": payload.external_ref,
            "owner": case.owner,
        },
    )
    db.commit()
    return CaseCreateResponse(case_id=case.case_id, status="created")


@app.get("/api/mock/records/{external_ref}")
def get_mock_records(external_ref: str) -> dict[str, Any]:
    bundle = get_record_bundle(external_ref)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Mock record bundle not found.")
    return bundle


@app.get("/api/cases/{case_id}/context", response_model=ContextSnapshot)
def get_case_context(
    case_id: str,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ContextSnapshot:
    case = _case_or_404(db, case_id)
    return _build_context_snapshot(db, case, refresh=refresh)


@app.post("/api/cases/{case_id}/analyze", response_model=AnalyzeCaseResponse)
async def analyze_case(case_id: str, db: Session = Depends(get_db)) -> AnalyzeCaseResponse:
    case = _case_or_404(db, case_id)
    context = _build_context_snapshot(db, case)
    case.status = "analyzing"
    _log_event(db, case.case_id, "analysis_started", {"at": _utc_iso()})
    db.commit()

    payload = {
        "case_id": case.case_id,
        "external_ref": case.external_ref,
        "anomaly_type": case.case_type,
        "user_description": case.user_description,
        "records": context.records,
        "rule_results": context.rule_results,
        "notes": context.notes,
        "matched_sop_refs": context.matched_sop_refs,
    }

    try:
        run_id, ai_result = await analyze_with_dify_or_fallback(payload)
    except Exception as exc:
        case.status = "failed"
        _log_event(db, case.case_id, "analysis_failed", {"error": str(exc)})
        db.commit()
        raise HTTPException(status_code=502, detail="Analysis failed.") from exc

    _store_ai_result(db, case, run_id, ai_result)
    case.status = "waiting_review" if ai_result["needs_human_review"] else "completed"
    _apply_sla(case, ai_result["risk_level"])
    _log_event(
        db,
        case.case_id,
        "analysis_completed",
        {
            "run_id": run_id,
            "risk_level": ai_result["risk_level"],
            "needs_human_review": ai_result["needs_human_review"],
        },
    )
    db.commit()

    return AnalyzeCaseResponse(
        run_id=run_id,
        current_status=case.status,
        ai_result=ai_result,
    )


@app.post("/api/cases/{case_id}/review")
def review_case(
    case_id: str,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    case = _case_or_404(db, case_id)
    ai_result = _latest_ai_result(db, case.case_id)
    if ai_result is None:
        raise HTTPException(status_code=409, detail="Case has not been analyzed yet.")

    review = CaseReview(
        case_id=case.case_id,
        reviewer=payload.reviewer,
        decision=payload.decision,
        comment=payload.comment,
    )
    db.add(review)
    if payload.decision == "approve":
        case.status = "completed"
    elif payload.decision == "reject":
        case.status = "rejected"
    else:
        case.status = "needs_more_info"
    _apply_sla(case, ai_result.risk_level)

    _log_event(
        db,
        case.case_id,
        "review_recorded",
        {
            "decision": payload.decision,
            "reviewer": payload.reviewer,
            "comment": payload.comment,
            "ai_review_reason": ai_result.review_reason,
        },
    )
    db.commit()
    return {"updated_status": case.status}


@app.post("/api/cases/{case_id}/assign")
def assign_case(
    case_id: str,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    case = _case_or_404(db, case_id)
    context = _latest_context(db, case.case_id)
    ai_row = _latest_ai_result(db, case.case_id)
    previous_owner = case.owner or _default_owner(case.case_type, case.external_ref)
    risk_level = _risk_level_for_case(case, context, ai_row)

    case.owner = payload.owner
    case.assigned_at = datetime.utcnow()
    if payload.reset_sla or case.due_at is None:
        _apply_sla(case, risk_level, base_time=case.assigned_at)

    _log_event(
        db,
        case.case_id,
        "assignment_updated",
        {
            "from_owner": previous_owner,
            "to_owner": payload.owner,
            "assigned_by": payload.assigned_by,
            "comment": payload.comment,
            "sla_status": _sla_status(case),
        },
    )
    db.commit()
    return {
        "owner": case.owner,
        "assigned_at": case.assigned_at,
        "due_at": case.due_at,
        "sla_status": _sla_status(case),
    }


@app.get("/api/cases/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(case_id: str, db: Session = Depends(get_db)) -> CaseDetailResponse:
    case = _case_or_404(db, case_id)
    context = _latest_context(db, case.case_id)
    ai_row = _latest_ai_result(db, case.case_id)
    review = _latest_review(db, case.case_id)
    audit_rows = db.scalars(
        select(CaseAuditLog)
        .where(CaseAuditLog.case_id == case.case_id)
        .order_by(CaseAuditLog.created_at.asc())
    ).all()

    return CaseDetailResponse(
        base_info={
            "case_id": case.case_id,
            "case_type": case.case_type,
            "external_ref": case.external_ref,
            "user_description": case.user_description,
            "notes": case.notes,
            "status": case.status,
            "owner": case.owner or _default_owner(case.case_type, case.external_ref),
            "queue_bucket": _queue_bucket(case.status),
            "assigned_at": case.assigned_at,
            "due_at": case.due_at,
            "sla_status": _sla_status(case),
            "created_at": case.created_at,
            "updated_at": case.updated_at,
        },
        records_snapshot=context.records_json if context else None,
        rule_results=context.rule_results_json if context else None,
        ai_result=_to_ai_result_payload(ai_row),
        review_result=(
            {
                "reviewer": review.reviewer,
                "decision": review.decision,
                "comment": review.comment,
                "created_at": review.created_at,
            }
            if review
            else None
        ),
        audit_logs=[
            AuditLogEntry(
                event_type=row.event_type,
                payload=row.payload_json,
                created_at=row.created_at,
            )
            for row in audit_rows
        ],
    )


@app.get("/api/cases")
def list_recent_cases(
    limit: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None),
    sla_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    all_rows = db.scalars(select(Case).order_by(desc(Case.updated_at))).all()
    items = []
    metrics = {
        "all_open": 0,
        "waiting_review": 0,
        "needs_more_info": 0,
        "overdue": 0,
        "high_risk": 0,
        "completed": 0,
    }
    for row in all_rows:
        context = _latest_context(db, row.case_id)
        ai_row = _latest_ai_result(db, row.case_id)
        rule_results = context.rule_results_json if context else {}
        risk_level = (ai_row.risk_level if ai_row else None) or rule_results.get("risk_level") or "low"
        bucket = _queue_bucket(row.status)
        current_sla_status = _sla_status(row)
        if bucket in {"waiting_review", "needs_more_info", "new"}:
            metrics["all_open"] += 1
        if row.status == "waiting_review":
            metrics["waiting_review"] += 1
        if row.status == "needs_more_info":
            metrics["needs_more_info"] += 1
        if current_sla_status == "overdue":
            metrics["overdue"] += 1
        if risk_level == "high":
            metrics["high_risk"] += 1
        if row.status == "completed":
            metrics["completed"] += 1

    for row in all_rows:
        context = _latest_context(db, row.case_id)
        ai_row = _latest_ai_result(db, row.case_id)
        rule_results = context.rule_results_json if context else {}
        risk_level = (ai_row.risk_level if ai_row else None) or rule_results.get("risk_level") or "low"
        bucket = _queue_bucket(row.status)
        current_sla_status = _sla_status(row)
        if status and status != "all" and row.status != status:
            continue
        if sla_status and sla_status != "all" and current_sla_status != sla_status:
            continue
        items.append(
            {
                "case_id": row.case_id,
                "case_type": row.case_type,
                "external_ref": row.external_ref,
                "status": row.status,
                "queue_bucket": bucket,
                "risk_level": risk_level,
                "rule_hit_count": len(rule_results.get("rule_hits", [])),
                "owner": row.owner or _default_owner(row.case_type, row.external_ref),
                "assigned_at": row.assigned_at,
                "due_at": row.due_at,
                "sla_status": current_sla_status,
                "updated_at": row.updated_at,
                "created_at": row.created_at,
                "summary": ai_row.summary if ai_row else row.user_description,
            }
        )
    return {
        "metrics": metrics,
        "items": items[:limit],
    }
