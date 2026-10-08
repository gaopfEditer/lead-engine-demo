from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'lead_engine.db'}")
    mock_sites_base_url: str = os.getenv("MOCK_SITES_BASE_URL", "http://127.0.0.1:8081")
    cslb_sample_path: Path = Path(os.getenv("CSLB_SAMPLE_PATH", BASE_DIR / "data" / "cslb_sample.csv"))
    icp_config_path: Path = Path(os.getenv("ICP_CONFIG_PATH", BASE_DIR / "presets" / "ca_contractors.yaml"))
    llm_base_url: str | None = os.getenv("LLM_BASE_URL")
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    hubspot_token: str | None = os.getenv("HUBSPOT_TOKEN")
    email_verifier: str = os.getenv("EMAIL_VERIFIER", "mock")
    demo_read_only: bool = os.getenv("DEMO_READ_ONLY", "").lower() in ("1", "true", "yes")
    # Mask CSLB personnel / owner names in UI, exports, and ingest (off for local full-data runs).
    public_demo: bool = os.getenv("PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
    user_agent: str = "ContractorLeadEngineDemo/1.0 (+https://github.com/demo; portfolio)"


settings = Settings()
