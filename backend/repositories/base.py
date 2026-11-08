"""Storage-agnostic repository contract.

Analytics and services depend only on this protocol, so the DuckDB implementation used
in Phase 1 can be replaced by a Databricks SQL implementation in Phase 2. Table names
are unqualified (e.g. "machine_day"); the Databricks implementation resolves them inside
the configured catalog and schema.
"""

from typing import Any, Protocol

import pandas as pd
import pyarrow as pa


class AnalyticsRepository(Protocol):
    dialect: str  # "duckdb" | "databricks" (see analytics/sql_dialect.py)

    def query(self, sql: str, params: dict[str, Any] | None = None) -> pa.Table: ...

    def query_df(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame: ...

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any: ...

    def write_table(self, name: str, table: pa.Table, mode: str = "overwrite") -> None: ...

    def describe(self, table: str) -> pd.DataFrame: ...

    def list_tables(self) -> list[str]: ...
