"""Central application settings, loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "dev", "test", "prod"] = "local"
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    # Data backend: "duckdb" in Phase 1, "databricks" in Phase 2
    data_backend: Literal["duckdb", "databricks"] = "duckdb"
    local_db_path: str = "data/processed/house_of_minds.duckdb"
    challenge_data_dir: str = "data/raw/dashboard-royale/data"
    reports_dir: str = "reports"
    evidence_store_path: str = "data/processed/evidence_ledger.jsonl"

    # LLM
    llm_provider: Literal["none", "openai", "databricks"] = "none"
    llm_model: str = ""
    llm_base_url: str | None = None

    # Databricks (auth comes from the CLI profile, never from this file)
    databricks_host: str | None = None
    databricks_profile: str | None = None
    databricks_warehouse_id: str | None = None
    databricks_catalog: str = "workspace"
    databricks_schema: str = "house_of_minds"

    # MLflow
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
