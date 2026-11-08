"""Phase 1 local repository backed by DuckDB."""

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow as pa


class DuckDBRepository:
    dialect = "duckdb"

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(path)

    def query(self, sql: str, params: dict[str, Any] | None = None) -> pa.Table:
        return self._con.sql(sql, params=params or None).to_arrow_table()

    def query_df(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        return self._con.execute(sql, params or {}).df()

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        rows = self._con.execute(sql, params or {}).fetchall()  # consume fully (DuckDB 2.x)
        return rows[0][0] if rows else None

    def write_table(self, name: str, table: pa.Table, mode: str = "overwrite") -> None:
        self._con.register("_incoming", table)
        if mode == "overwrite":
            self._con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _incoming')
        else:
            self._con.execute(f'INSERT INTO "{name}" SELECT * FROM _incoming')
        self._con.unregister("_incoming")

    def register_parquet_view(self, name: str, parquet_path: str) -> None:
        safe = parquet_path.replace("'", "''")
        self._con.execute(
            f"CREATE OR REPLACE VIEW \"{name}\" AS SELECT * FROM read_parquet('{safe}')"
        )

    def describe(self, table: str) -> pd.DataFrame:
        """Columns and types as (column_name, column_type)."""
        df = self._con.execute(f'DESCRIBE SELECT * FROM "{table}"').df()
        return df[["column_name", "column_type"]]

    def list_tables(self) -> list[str]:
        return [r[0] for r in self._con.execute("SHOW TABLES").fetchall()]
