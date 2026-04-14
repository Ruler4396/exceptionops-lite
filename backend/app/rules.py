from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_rules(bundle: dict[str, Any]) -> dict[str, Any]:
    records = bundle["records"]
    po = records["purchase_order"]
    receipt = records["goods_receipt"]
    invoice = records["invoice"]
    status_log = records["shipment_or_status_log"]

    rule_hits: list[dict[str, Any]] = []
    risk_flags: list[str] = []
    anomaly_votes: list[str] = []

    po_amount = float(po.get("total_amount", 0) or 0)
    invoice_amount = float(invoice.get("total_amount", 0) or 0)
    if abs(po_amount - invoice_amount) >= 0.01:
        rule_hits.append(
            {
                "rule_code": "AMOUNT_MISMATCH",
                "severity": "high" if abs(po_amount - invoice_amount) >= 1000 else "medium",
                "message": f"PO total {po_amount:.2f} and invoice total {invoice_amount:.2f} are inconsistent.",
                "evidence_refs": [
                    "purchase_order.total_amount",
                    "invoice.total_amount",
                    "invoice.currency",
                ],
                "suggested_next_checks": [
                    "检查发票是否包含未经批准的附加费用行。",
                    "核对应付金额与采购审批说明是否一致。",
                ],
            }
        )
        risk_flags.append("amount_adjustment")
        anomaly_votes.append("amount_mismatch")

    ordered_qty = int(po.get("ordered_qty", 0) or 0)
    received_qty = int(receipt.get("received_qty", 0) or 0)
    billed_qty = int(invoice.get("billed_qty", 0) or 0)
    if len({ordered_qty, received_qty, billed_qty}) > 1:
        rule_hits.append(
            {
                "rule_code": "QUANTITY_MISMATCH",
                "severity": "medium" if received_qty == billed_qty else "high",
                "message": (
                    f"Ordered qty {ordered_qty}, received qty {received_qty}, billed qty {billed_qty} do not align."
                ),
                "evidence_refs": [
                    "purchase_order.ordered_qty",
                    "goods_receipt.received_qty",
                    "invoice.billed_qty",
                ],
                "suggested_next_checks": [
                    "确认是否为部分收货或异常超收。",
                    "将发票行与收货记录逐项核对。",
                ],
            }
        )
        anomaly_votes.append("quantity_mismatch")

    status_triplet = {
        "po": po.get("status"),
        "receipt": receipt.get("status"),
        "invoice": invoice.get("status"),
        "shipment": status_log[-1]["status"] if status_log else None,
    }
    if status_triplet["invoice"] == "approved" and status_triplet["receipt"] != "received":
        rule_hits.append(
            {
                "rule_code": "STATUS_CONFLICT",
                "severity": "high",
                "message": "Invoice is approved before the receipt is confirmed, creating a settlement conflict.",
                "evidence_refs": [
                    "goods_receipt.status",
                    "invoice.status",
                    "shipment_or_status_log[-1].status",
                ],
                "suggested_next_checks": [
                    "在收货状态明确前冻结结算动作。",
                    "通知仓储核验最新物流状态。",
                ],
            }
        )
        risk_flags.append("status_change")
        anomaly_votes.append("status_conflict")
    elif status_triplet["shipment"] == "delivered" and status_triplet["receipt"] not in {"received", "closed"}:
        rule_hits.append(
            {
                "rule_code": "STATUS_CONFLICT",
                "severity": "medium",
                "message": "Logistics shows delivered but the receiving document is not closed.",
                "evidence_refs": [
                    "shipment_or_status_log[-1].status",
                    "goods_receipt.status",
                ],
                "suggested_next_checks": [
                    "确认收货扫描是否延迟入账。",
                    "核查仓库是否拒收该批货物。",
                ],
            }
        )
        risk_flags.append("status_change")
        anomaly_votes.append("status_conflict")

    critical_fields = {
        "invoice.invoice_number": invoice.get("invoice_number"),
        "goods_receipt.receiver_id": receipt.get("receiver_id"),
        "shipment_or_status_log[-1].tracking_number": status_log[-1].get("tracking_number") if status_log else None,
    }
    missing_fields = [ref for ref, value in critical_fields.items() if value in (None, "", [])]
    if missing_fields:
        rule_hits.append(
            {
                "rule_code": "MISSING_CRITICAL_FIELD",
                "severity": "high",
                "message": "One or more critical fields are missing from the evidence bundle.",
                "evidence_refs": missing_fields,
                "suggested_next_checks": [
                    "先补齐缺失源单据，再做最终判断。",
                    "在字段补齐前禁止自动下游变更。",
                ],
            }
        )
        risk_flags.append("missing_critical_field")
        anomaly_votes.append("field_missing")

    updated_times = [
        _to_utc(_parse_dt(po.get("updated_at"))),
        _to_utc(_parse_dt(receipt.get("updated_at"))),
        _to_utc(_parse_dt(invoice.get("updated_at"))),
        *[_to_utc(_parse_dt(item.get("updated_at"))) for item in status_log],
    ]
    updated_times = [item for item in updated_times if item is not None]
    if updated_times:
        hours_since_last = (datetime.now(timezone.utc) - max(updated_times)).total_seconds() / 3600
        if hours_since_last > 72 and any(hit["severity"] in {"medium", "high"} for hit in rule_hits):
            rule_hits.append(
                {
                    "rule_code": "STALE_UPDATE",
                    "severity": "medium",
                    "message": f"No system update has landed for {hours_since_last:.1f} hours while the case remains unresolved.",
                    "evidence_refs": [
                        "purchase_order.updated_at",
                        "goods_receipt.updated_at",
                        "invoice.updated_at",
                    ],
                "suggested_next_checks": [
                    "升级到责任系统并刷新最新状态。",
                    "确认案例是否卡在人工交接环节。",
                ],
            }
        )
            risk_flags.append("stale_exception")

    if len(rule_hits) >= 2:
        risk_flags.append("multiple_possible_causes")
    if any(hit["rule_code"] == "MISSING_CRITICAL_FIELD" for hit in rule_hits):
        risk_flags.append("insufficient_evidence")

    severity_order = {"low": 0, "medium": 1, "high": 2}
    highest = max((severity_order[hit["severity"]] for hit in rule_hits), default=0)
    risk_level = "high" if highest == 2 else "medium" if highest == 1 else "low"
    normalized_anomaly_type = anomaly_votes[0] if anomaly_votes else bundle.get("default_anomaly_type", "unknown")
    needs_human_review = any(
        flag in risk_flags
        for flag in [
            "amount_adjustment",
            "status_change",
            "missing_critical_field",
            "multiple_possible_causes",
            "insufficient_evidence",
        ]
    )

    return {
        "normalized_anomaly_type": normalized_anomaly_type,
        "risk_level": risk_level,
        "needs_human_review": needs_human_review,
        "risk_flags": sorted(set(risk_flags)),
        "rule_hits": rule_hits,
    }
