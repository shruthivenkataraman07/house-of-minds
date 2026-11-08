from config.settings import Settings, get_settings

from .base import AnalyticsRepository
from .databricks_repo import DatabricksRepository
from .duckdb_repo import DuckDBRepository


def get_repository(settings: Settings | None = None) -> AnalyticsRepository:
    s = settings or get_settings()
    if s.data_backend == "databricks":
        if not s.databricks_warehouse_id:
            raise ValueError("DATABRICKS_WAREHOUSE_ID is required for DATA_BACKEND=databricks")
        return DatabricksRepository(
            s.databricks_warehouse_id,
            s.databricks_catalog,
            s.databricks_schema,
            s.databricks_profile,
        )
    return DuckDBRepository(s.local_db_path)
