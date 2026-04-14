from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from .config import settings
from .schemas import AIAnalysisResult


REQUIRED_OUTPUT_FIELDS = {
    "summary",
    "anomaly_type",
    "evidence_used",
    "possible_causes",
    "recommended_action",
    "risk_level",
    "needs_human_review",
    "review_reason",
    "audit_payload",
}


def _extract_value(records: dict[str, Any], ref: str) -> Any:
    current: Any = records
    path = ref.replace("[-1]", ".-1").split(".")
    for part in path:
        if part == "-1":
            if not isinstance(current, list) or not current:
                return None
            current = current[-1]
            continue
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current


def _map_anomaly_label(value: str) -> str:
    mapping = {
        "amount_mismatch": "金额不一致",
        "quantity_mismatch": "数量不一致",
        "status_conflict": "状态冲突",
        "field_missing": "关键字段缺失",
        "stale_exception": "超时未处理",
        "cross_system_exception": "跨系统异常",
        "normal": "正常对照",
    }
    return mapping.get(value, value)


def _build_human_summary(payload: dict[str, Any], rule_results: dict[str, Any]) -> str:
    records = payload["records"]
    po = records["purchase_order"]
    receipt = records["goods_receipt"]
    invoice = records["invoice"]
    status_log = records.get("shipment_or_status_log") or []
    last_status = status_log[-1]["status"] if status_log else "无"

    summary_parts: list[str] = []
    codes = {hit["rule_code"] for hit in rule_results["rule_hits"]}
    anomaly_label = _map_anomaly_label(rule_results["normalized_anomaly_type"])

    if "AMOUNT_MISMATCH" in codes:
        summary_parts.append(
            f"采购单金额 {po.get('total_amount')} 与发票金额 {invoice.get('total_amount')} 不一致"
        )
    if "QUANTITY_MISMATCH" in codes:
        summary_parts.append(
            f"采购数量 {po.get('ordered_qty')}、收货数量 {receipt.get('received_qty')}、开票数量 {invoice.get('billed_qty')} 存在差异"
        )
    if "STATUS_CONFLICT" in codes:
        summary_parts.append(
            f"收货状态为 {receipt.get('status')}，发票状态为 {invoice.get('status')}，物流最新状态为 {last_status}"
        )
    if "MISSING_CRITICAL_FIELD" in codes:
        missing = []
        if not receipt.get("receiver_id"):
            missing.append("收货人")
        if not invoice.get("invoice_number"):
            missing.append("发票号")
        if status_log and not status_log[-1].get("tracking_number"):
            missing.append("物流单号")
        if missing:
            summary_parts.append(f"关键字段缺失：{'、'.join(missing)}")
    if "STALE_UPDATE" in codes:
        summary_parts.append("该异常已长时间未更新")

    if not summary_parts:
        return f"单号 {payload['external_ref']} 当前未发现明显冲突，系统判断为{anomaly_label}。"

    tail = (
        "当前建议进入人工确认。"
        if rule_results["needs_human_review"]
        else "当前可按低风险路径继续处理。"
    )
    return f"单号 {payload['external_ref']} 存在{anomaly_label}：{'；'.join(summary_parts)}。{tail}"


def build_local_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload["records"]
    rule_results = payload["rule_results"]
    matched_sops = payload["matched_sop_refs"]
    notes = payload["notes"]
    rule_hits = rule_results["rule_hits"]
    evidence_used = []
    for hit in rule_hits:
        for ref in hit["evidence_refs"]:
            evidence_used.append(
                {
                    "ref": ref,
                    "value": _extract_value(records, ref),
                    "source_rule": hit["rule_code"],
                }
            )

    causes: list[str] = []
    recommendations: list[str] = []
    for hit in rule_hits:
        if hit["rule_code"] == "AMOUNT_MISMATCH":
            causes.append("发票金额与采购单批准金额不一致，可能存在附加费用或未审批差异。")
            recommendations.append("在确认供应商附加费用或审批说明前，暂停任何金额调整。")
        if hit["rule_code"] == "QUANTITY_MISMATCH":
            causes.append("收货数量与开票数量不一致，可能是部分收货或发票行项目错误。")
            recommendations.append("先完成收货行与发票行对账，再关闭案例。")
        if hit["rule_code"] == "STATUS_CONFLICT":
            causes.append("下游状态先于上游业务确认推进，存在跨系统状态越位。")
            recommendations.append("在仓库和财务对最终状态达成一致前，冻结状态变更动作。")
        if hit["rule_code"] == "MISSING_CRITICAL_FIELD":
            causes.append("关键证据字段缺失，系统无法安全收敛到单一根因。")
            recommendations.append("补齐缺失源字段后，再决定是否执行纠正动作。")
        if hit["rule_code"] == "STALE_UPDATE":
            causes.append("异常长时间未更新，可能存在责任人断点或交接中断。")
            recommendations.append("升级到责任系统并刷新最新记录快照。")

    if matched_sops:
        recommendations.extend([f"参照 SOP：{item['title']}" for item in matched_sops[:2]])
    if notes.get("similar_case_summaries"):
        causes.append(f"历史相似模式：{notes['similar_case_summaries'][0]}")

    summary = _build_human_summary(payload, rule_results)

    output = {
        "summary": summary,
        "anomaly_type": rule_results["normalized_anomaly_type"],
        "evidence_used": evidence_used[:8],
        "possible_causes": list(dict.fromkeys(causes))[:5]
        or ["当前证据不足，无法进一步缩小根因范围。"],
        "recommended_action": list(dict.fromkeys(recommendations))[:6]
        or ["当前缺少安全的自动化建议，请升级到人工审核。"],
        "risk_level": rule_results["risk_level"],
        "needs_human_review": rule_results["needs_human_review"],
        "review_reason": (
            "检测到高风险调整、状态变更或证据缺口。"
            if rule_results["needs_human_review"]
            else "当前规则证据足够稳定，可支撑低风险处理建议。"
        ),
        "audit_payload": {
            "provider": "local_fallback",
            "rule_codes": [hit["rule_code"] for hit in rule_hits],
            "matched_sops": matched_sops,
            "risk_flags": rule_results["risk_flags"],
        },
    }
    return AIAnalysisResult.model_validate(output).model_dump()


def _validate_output(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("Dify output must be a JSON object.")
    missing = REQUIRED_OUTPUT_FIELDS - set(output.keys())
    if missing:
        raise ValueError(f"Dify output missing fields: {sorted(missing)}")
    return AIAnalysisResult.model_validate(output).model_dump()


async def analyze_with_dify_or_fallback(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not settings.dify_enabled:
        return f"local-{uuid.uuid4().hex[:10]}", build_local_analysis(payload)

    url = settings.dify_api_url.rstrip("/") + "/v1/workflows/run"
    headers = {
        "Authorization": f"Bearer {settings.dify_api_key}",
        "Content-Type": "application/json",
    }
    request_body = {
        "inputs": payload,
        "response_mode": "blocking",
        "user": settings.dify_user,
        "workflow_id": settings.dify_workflow_id,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=request_body)
            response.raise_for_status()
    except Exception:
        return f"local-{uuid.uuid4().hex[:10]}", build_local_analysis(payload)

    body = response.json()
    raw_outputs = body.get("data", {}).get("outputs") or body.get("outputs") or body.get("data")
    if isinstance(raw_outputs, str):
        raw_outputs = json.loads(raw_outputs)
    validated = _validate_output(raw_outputs)
    run_id = body.get("workflow_run_id") or body.get("task_id") or f"dify-{uuid.uuid4().hex[:10]}"
    return run_id, validated
