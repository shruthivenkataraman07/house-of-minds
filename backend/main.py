"""House of Minds API + web app (single origin).

FastAPI serves /api/v1 (read-only dashboard API) and, when built, the static React app
from web/out with an SPA fallback. CORS is enabled only for origins listed in
HOM_CORS_ORIGINS (local development with `next dev`).

Run: uv run uvicorn backend.main:app --port 8000
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.api.v1 import router
from backend.services.source import DataUnavailable

logging.basicConfig(level=logging.INFO)
WEB = Path(__file__).resolve().parents[1] / "web" / "out"
RECOVERY = {
    404: "Check the identifier; list valid ones via the collection endpoint.",
    422: "Fix the highlighted parameter and retry.",
    503: "Retry shortly; the validated snapshot remains available.",
}

app = FastAPI(
    title="House of Minds API",
    version="1.0.0",
    description="Read-only decision API over validated Gilded Ace analytics.",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
origins = [o for o in os.environ.get("HOM_CORS_ORIGINS", "").split(",") if o]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
app.include_router(router)


@app.get("/api/health", include_in_schema=False)
def legacy_health() -> dict[str, str]:
    """Original health route (kept for existing checks); see /api/v1/health."""
    return {"status": "ok", "data_mode": os.environ.get("HOM_DATA_MODE", "snapshot")}


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        {
            "error": "request_failed",
            "detail": str(exc.detail),
            "recovery": RECOVERY.get(exc.status_code, "Retry the request."),
        },
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []))
    return JSONResponse(
        {
            "error": "invalid_parameter",
            "detail": f"{where}: {first.get('msg', 'invalid')}",
            "recovery": RECOVERY[422],
        },
        status_code=422,
    )


@app.exception_handler(DataUnavailable)
async def data_error(_: Request, exc: DataUnavailable) -> JSONResponse:
    return JSONResponse(
        {"error": "data_unavailable", "detail": str(exc), "recovery": RECOVERY[503]},
        status_code=503,
    )


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str) -> FileResponse:
    """Static React build with SPA fallback (unknown non-API paths -> index.html)."""
    if path.startswith("api/"):
        raise HTTPException(404, "unknown API route")
    if path.startswith("data/"):  # raw exports are served only through the API
        raise HTTPException(404, "not found")
    if not WEB.exists():
        raise HTTPException(404, "web build missing: run `cd web && npm run build`")
    target = (WEB / path).resolve()
    if path and target.is_file() and WEB in target.parents:
        cache = (
            "public, max-age=31536000, immutable" if "/_next/static/" in f"/{path}" else "no-cache"
        )
        return FileResponse(target, headers={"Cache-Control": cache})
    html = WEB / f"{path}.html" if path else WEB / "index.html"
    return FileResponse(
        html if html.is_file() else WEB / "index.html", headers={"Cache-Control": "no-cache"}
    )
