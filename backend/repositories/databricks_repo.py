"""Phase 2 repository backed by a Databricks SQL warehouse and Unity Catalog.

Authentication uses the Databricks CLI OAuth profile (or the job's runtime identity);
no tokens are stored in code or config. Table names stay unqualified: every session runs
`USE CATALOG` / `USE SCHEMA` so the same analytics SQL works on DuckDB and Databricks.
"""

from __future__ import annotations

import atexit
import contextlib
import io
import re
import uuid
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

from databricks import sql as dbsql

RAW_VOLUME = "raw"
STAGING_DIR = "_staging"


class DatabricksRepository:
    dialect = "databricks"

    def __init__(self, warehouse_id: str, catalog: str, schema: str, profile: str | None) -> None:
        self.warehouse_id = warehouse_id
        self.catalog = catalog
        self.schema = schema
        self.profile = profile
        self._cfg = Config(profile=profile) if profile else Config()
        self._ws = WorkspaceClient(config=self._cfg)
        self._con = dbsql.connect(
            server_hostname=self._cfg.host.removeprefix("https://").rstrip("/"),
            http_path=f"/sql/1.0/warehouses/{warehouse_id}",
            credentials_provider=lambda: self._cfg.authenticate,
            catalog=catalog,
            schema=schema,
            session_configuration={"TIMEZONE": "UTC", "ANSI_MODE": "true"},
        )
        atexit.register(self.close)

    # ---- reads ---------------------------------------------------------------------------
    def query(self, sql: str, params: dict[str, Any] | None = None) -> pa.Table:
        if params:  # DuckDB-style $name placeholders -> Databricks native :name markers
            sql = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", r":\1", sql)
        with self._con.cursor() as cur:
            cur.execute(sql, params or None)
            if cur.description is None:
                return pa.table({})
            return _decimals_to_float(cur.fetchall_arrow())

    def query_df(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        return self.query(sql, params).to_pandas()

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        t = self.query(sql, params)
        if t.num_rows == 0:
            return None
        return t.column(0)[0].as_py()

    def execute(self, sql: str) -> None:
        with self._con.cursor() as cur:
            cur.execute(sql)

    def describe(self, table: str) -> pd.DataFrame:
        df = self.query_df(f"DESCRIBE TABLE `{table}`")
        df = df[~df.col_name.str.startswith("#") & (df.col_name != "")]
        return pd.DataFrame({"column_name": df.col_name,
                             "column_type": df.data_type.map(_spark_type_to_duck)})

    def list_tables(self) -> list[str]:
        df = self.query_df(f"SHOW TABLES IN `{self.catalog}`.`{self.schema}`")
        return df.tableName.tolist()

    # ---- writes --------------------------------------------------------------------------
    def write_table(self, name: str, table: pa.Table, mode: str = "overwrite") -> None:
        """Stage the Arrow table as Parquet in the volume, then CTAS / INSERT into Delta."""
        path = (f"/Volumes/{self.catalog}/{self.schema}/{RAW_VOLUME}/{STAGING_DIR}/"
                f"{name}-{uuid.uuid4().hex[:8]}.parquet")
        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)
        self._ws.files.upload(path, buf, overwrite=True)
        src = f"read_files('{path}', format => 'parquet')"
        try:
            if mode == "overwrite":
                self.execute(f"CREATE OR REPLACE TABLE `{name}` AS SELECT * FROM {src}")
            else:
                self.execute(f"INSERT INTO `{name}` SELECT * FROM {src}")
        finally:
            self._ws.files.delete(path)

    def close(self) -> None:
        with contextlib.suppress(Exception):  # already closed / interpreter shutdown
            self._con.close()


def _decimals_to_float(t: pa.Table) -> pa.Table:
    """Match DuckDB's .df(): DECIMAL columns become float64 for pandas arithmetic."""
    cols = []
    for f, col in zip(t.schema, t.columns, strict=True):
        cols.append(col.cast(pa.float64()) if pa.types.is_decimal(f.type) else col)
    return pa.table(cols, names=t.schema.names)


def _spark_type_to_duck(t: str) -> str:
    t = t.lower()
    mapping = {"string": "VARCHAR", "bigint": "BIGINT", "int": "INTEGER", "double": "DOUBLE",
               "boolean": "BOOLEAN", "date": "DATE", "float": "FLOAT", "smallint": "SMALLINT",
               "tinyint": "TINYINT"}
    if t.startswith("decimal"):
        return t.upper()
    if t.startswith("timestamp"):
        return "TIMESTAMP"
    return mapping.get(t, t.upper())
