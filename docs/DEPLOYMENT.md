# House of Minds: run and deploy

The app has three layers:

| Layer | What it is |
|---|---|
| React (Next.js static export) | `web/out` |
| FastAPI | `backend/main.py`: serves `/api/v1` and the static app from one origin |
| Databricks Unity Catalog | Source of truth for the `ch_*` / `dash_*` tables |

## Data modes

Set the mode server-side with `HOM_DATA_MODE`.

| Mode | Source | Credentials | UI label |
|---|---|---|---|
| `snapshot` (default) | `web/public/data/current` + `sidecar`, SHA-256 verified | none | "Validated snapshot" |
| `databricks` | Allowlisted UC tables via the SQL warehouse; 15-minute cache; snapshot fallback per dataset | server-side only | "Live · Databricks" |

In live mode, every response's `meta.served_from` reports `databricks`, `snapshot` or `mixed`. The daily grains and audit datasets always come from the snapshot, because they are not in Unity Catalog.

## Local

```bash
uv sync && (cd web && npm ci)
cd web && npm run build && cd ..                         # static React build -> web/out
uv run uvicorn backend.main:app --port 8000               # http://localhost:8000  (API docs: /docs)
# live mode (uses your Databricks CLI profile from .env):
HOM_DATA_MODE=databricks uv run uvicorn backend.main:app --port 8000
# frontend dev with hot reload (separate origin):
HOM_CORS_ORIGINS=http://localhost:3000 uv run uvicorn backend.main:app --port 8000 &
cd web && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

## Container (any Python/Docker host)

```bash
docker build -t house-of-minds .
docker run -p 8000:8000 house-of-minds                    # snapshot mode, no secrets
```

- **Health check:** `GET /api/v1/health`
- **Routing:** the SPA fallback serves `index.html` for any non-API path. Raw `data/` files are not served.
- **Live mode on a host:** set `HOM_DATA_MODE=databricks`, `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_CATALOG` and `DATABRICKS_SCHEMA`, plus a read-only service principal (`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`) from the host's secret store.

- **Image contents:** the image installs only `requirements-web.txt` (FastAPI, Uvicorn, Pydantic). Build with `--build-arg WITH_DATABRICKS=true` to add the optional live-mode packages from `requirements-databricks.txt`.

## Public access: Render Free web service

Judges need a host that serves anonymous HTTPS. Databricks Apps require a workspace login, so they don't meet that requirement. The project deploys to Render with `render.yaml`:

| Setting | Value |
|---|---|
| Services | One web service, `plan: free` |
| Runtime | Docker |
| Health check | `/api/v1/health` |
| Data mode | `HOM_DATA_MODE=snapshot` |
| Extras | No database, disk or paid add-on |

**Steps** (each needs the repository owner):
1. Commit and push this repository to GitHub (`main`).
2. At render.com, sign in with GitHub and authorize Render to read the repository.
3. Choose **New → Blueprint**, select the repository, and confirm the service `house-of-minds` with instance type **Free**.
4. Wait for the first build (about 3–5 minutes). Then open `https://house-of-minds.onrender.com` (Render shows the actual URL).

**Free-tier behaviour:**
- The service sleeps after about 15 minutes without traffic. The next request takes up to about a minute while it wakes.
- Free instances have 512 MB RAM and a monthly free-hours allowance per workspace.

**Snapshot refresh:**
1. Run the validated pipeline, then `scripts/export_web_snapshot.py` and `scripts/export_dashboard_sidecar.py`.
2. Run the tests.
3. Commit and push. `autoDeploy: true` rebuilds the service.

There are no hand-edited metrics: every figure comes from the files in `web/public/data/`. The header shows the snapshot export date.

## Security

- **Read-only:** the API is `GET` only, plus `POST /api/v1/ask`, which never writes.
- **No user-controlled SQL:** live mode runs only `SELECT * FROM <allowlisted table>`.
- **Input validation:** every parameter is validated by pattern or range; invalid input returns `{error, detail, recovery}`.
- **No browser credentials:** the browser never receives Databricks credentials, and the frontend bundle has no secrets.
