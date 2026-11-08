# Troubleshooting

| Symptom | Fix |
| --- | --- |
| `lightgbm` import: `Library not loaded: @rpath/libomp.dylib` | `brew install libomp` |
| MLflow: "filesystem tracking backend is in maintenance mode" | Use `MLFLOW_TRACKING_URI=sqlite:///mlflow.db` (default in settings) |
| DuckDB: `no attribute fetch_arrow_table` | DuckDB 2.x renamed it to `to_arrow_table()` |
| `code: command not found` | VS Code → Command Palette → "Shell Command: Install 'code' command in PATH" |
| `databricks ...: unknown flag: --profile X` in zsh scripts | zsh doesn't split `$VAR` into words; write `-p HOUSE_OF_MINDS` inline |
| Databricks `401` / expired session | Re-run `databricks auth login --profile HOUSE_OF_MINDS` |
| npm `install-scripts` warning for `fsevents` | Harmless; fsevents is optional. Approve with `npm install-scripts approve fsevents` if wanted |
| Wrong Python version in `.venv` | `rm -rf .venv && uv sync` (uses `.python-version` = 3.12) |
| Playwright: browser not found | `cd frontend && npx playwright install chromium` |
| Port 5173 / 8000 in use | `lsof -i :5173` then stop that process, or set `BACKEND_PORT` |
