# Project instructions for coding agents

## Commands
- Python: `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`, `uv run mypy backend config`
- Frontend (in `frontend/`): `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, `npm run test:e2e`
- Everything: `scripts/verify.sh`
- Add Python deps with `uv add <pkg>` (updates `uv.lock`); frontend deps with `npm install` in `frontend/`.

## Architecture rules
- Keep data access, API routes, analytics, agent orchestration, and UI in their own modules.
- Services use `AnalyticsRepository` only; never import duckdb or databricks clients directly in services.
- Settings come from `config.settings.get_settings()`; no hard-coded hosts, paths, or IDs.
- Gaming day runs 6 a.m. to 6 a.m. local. Use ratio-of-sums for hold. Split models by time, never randomly.

## Safety rules
- Never put credentials in source or `.env.example`. Databricks auth uses the `HOUSE_OF_MINDS` CLI OAuth profile.
- Do not create or start Databricks clusters, warehouses, jobs, or serving endpoints without explicit user approval.
- Do not make paid LLM calls without approval; tests must use stubs.
- Do not run `curl | sh` installers; the Databricks CLI is installed via Homebrew.

## Git
- Do not commit unless the user asks. Preserve the user's git identity.
- Do not add AI co-author trailers or promotional AI attribution in commits, code, or docs.
- Record AI assistance in `docs/AI_USE_LOG.md` (required by the challenge's AI-use disclosure).
