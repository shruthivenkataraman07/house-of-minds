"""FastAPI entrypoint. Routers are added under backend/api in Phase 1."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings

settings = get_settings()

app = FastAPI(title="The House of Minds API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env, "data_backend": settings.data_backend}
