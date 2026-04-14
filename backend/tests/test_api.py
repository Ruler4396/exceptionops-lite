from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCEPTIONOPS_DATABASE_URL"] = f"sqlite:///{Path(__file__).resolve().parent / 'test.db'}"

from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db


client = TestClient(app)


def setup_module() -> None:
    test_db = Path(__file__).resolve().parent / "test.db"
    if test_db.exists():
        test_db.unlink()
    init_db()


def teardown_module() -> None:
    test_db = Path(__file__).resolve().parent / "test.db"
    if test_db.exists():
        test_db.unlink()


def test_create_context_analyze_and_review_flow() -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "anomaly_type": "cross_system_exception",
            "external_ref": "PO-2026-004",
            "user_description": "Invoice and receiving data look inconsistent after settlement approval.",
            "notes": "Escalated by finance analyst.",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    case_id = payload["case_id"]
    assert payload["status"] == "created"

    context_response = client.get(f"/api/cases/{case_id}/context")
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["rule_results"]["rule_hits"]
    assert context_payload["matched_sop_refs"]

    analyze_response = client.post(f"/api/cases/{case_id}/analyze")
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["ai_result"]["summary"]
    assert analysis["current_status"] in {"waiting_review", "completed"}

    review_response = client.post(
        f"/api/cases/{case_id}/review",
        json={
            "reviewer": "ops.lead@example.com",
            "decision": "approve",
            "comment": "Proceed with supplier clarification and keep manual lock.",
        },
    )
    assert review_response.status_code == 200
    assert review_response.json()["updated_status"] == "completed"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["review_result"]["decision"] == "approve"
    assert len(detail["audit_logs"]) >= 4
