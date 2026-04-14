def main(records, rule_results, notes, matched_sop_refs):
    rule_hits = rule_results.get("rule_hits", [])
    compact_records = {
        "purchase_order": records.get("purchase_order", {}),
        "goods_receipt": records.get("goods_receipt", {}),
        "invoice": records.get("invoice", {}),
        "last_status": (records.get("shipment_or_status_log") or [{}])[-1],
    }
    return {
        "compact_records": compact_records,
        "rule_snapshot": {
            "normalized_anomaly_type": rule_results.get("normalized_anomaly_type"),
            "risk_level": rule_results.get("risk_level"),
            "risk_flags": rule_results.get("risk_flags", []),
            "rule_hits": rule_hits,
        },
        "prompt_query": " ".join(
            [
                rule_results.get("normalized_anomaly_type", "exception"),
                notes.get("sop_hint", ""),
                " ".join(hit.get("rule_code", "") for hit in rule_hits),
            ]
        ).strip(),
        "notes": notes,
        "matched_sop_refs": matched_sop_refs,
    }

