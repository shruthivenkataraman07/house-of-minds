# Databricks configuration

Workspace: `https://dbc-f153929c-62ed.cloud.databricks.com` (AWS, Unity Catalog enabled)

## Authenticate (OAuth, no tokens in files)

```sh
databricks auth login --host https://dbc-f153929c-62ed.cloud.databricks.com --profile HOUSE_OF_MINDS
databricks auth describe --profile HOUSE_OF_MINDS
databricks current-user me --profile HOUSE_OF_MINDS
```

The OAuth token is cached by the CLI under `~/.databricks/`; `~/.databrickscfg` stores only the host and auth type.
Python uses the same profile: `WorkspaceClient(profile="HOUSE_OF_MINDS")`.

## Discovered resources (Step 1, read-only)

| Resource | Value |
| --- | --- |
| SQL warehouse | `Serverless Starter Warehouse` (`490ef3abcd3bd599`), Small, serverless. Stopped |
| Clusters | None |
| Catalogs | `workspace` (default), `system`, `samples` |
| Schemas in `workspace` | `default`, `information_schema` |
| Your privileges | Workspace admin; `CREATE TABLE / VOLUME / MODEL / FUNCTION / MATERIALIZED VIEW` on `workspace.default` |
| Runtimes offered | 16.4 LTS, 17.3 LTS, 18 LTS |
| Foundation models | Pay-per-token endpoints such as `databricks-meta-llama-3-3-70b-instruct`, `databricks-gpt-oss-120b`, `databricks-qwen3-next-80b-a3b-instruct`, `databricks-gte-large-en` |

## Phase 2 plan (not started)
1. Create schema `workspace.house_of_minds` (needs approval).
2. Upload Parquet files to a UC volume, then write Delta tables.
3. Set `DATABRICKS_WAREHOUSE_ID=490ef3abcd3bd599` and `DATA_BACKEND=databricks`.
4. Install Databricks Connect matching the compute: `uv add "databricks-connect==<serverless or DBR version>.*"`.
   Do not install standalone `pyspark` alongside it.
5. MLflow on Databricks: `MLFLOW_TRACKING_URI=databricks`, registry `databricks-uc`.

## Cost guardrails
The warehouse auto-starts when queried. Starting it, creating clusters, running jobs, or calling model endpoints
costs money. Each needs explicit approval.

The legacy pip package `databricks-cli` is deprecated; the Homebrew CLI replaces it.
