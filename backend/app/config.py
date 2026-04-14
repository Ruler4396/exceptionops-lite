from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data"
SEED_DIR = PROJECT_ROOT / "seed"


@dataclass(frozen=True)
class Settings:
    app_name: str = "ExceptionOps Lite"
    database_url: str = os.getenv(
        "EXCEPTIONOPS_DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'exceptionops.db').resolve()}",
    )
    dify_api_url: str | None = os.getenv("DIFY_API_URL")
    dify_api_key: str | None = os.getenv("DIFY_API_KEY")
    dify_workflow_id: str | None = os.getenv("DIFY_WORKFLOW_ID")
    dify_user: str = os.getenv("DIFY_WORKFLOW_USER", "exceptionops-lite")
    request_timeout_seconds: float = float(os.getenv("DIFY_TIMEOUT_SECONDS", "25"))

    @property
    def dify_enabled(self) -> bool:
        return bool(self.dify_api_url and self.dify_api_key and self.dify_workflow_id)


settings = Settings()

