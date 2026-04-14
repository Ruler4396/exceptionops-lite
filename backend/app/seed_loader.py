from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import SEED_DIR


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_mock_records() -> dict[str, Any]:
    return _load_json(SEED_DIR / "mock_records.json")


@lru_cache(maxsize=1)
def load_sop_catalog() -> dict[str, Any]:
    return _load_json(SEED_DIR / "knowledge_base_manifest.json")


def get_record_bundle(external_ref: str) -> dict[str, Any] | None:
    payload = load_mock_records()
    for item in payload["records"]:
        if item["external_ref"] == external_ref:
            return item
    return None


def iter_record_bundles() -> list[dict[str, Any]]:
    return list(load_mock_records()["records"])


def match_sops(rule_codes: list[str]) -> list[dict[str, str]]:
    catalog = load_sop_catalog()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for sop in catalog["documents"]:
        if any(tag in rule_codes for tag in sop["rule_tags"]):
            if sop["id"] in seen:
                continue
            seen.add(sop["id"])
            results.append(
                {
                    "id": sop["id"],
                    "title": sop["title"],
                    "path": sop["path"],
                }
            )
    return results
