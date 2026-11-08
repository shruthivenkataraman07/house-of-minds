# Environment setup

Verified on macOS 26.6 (Apple Silicon).

| Tool | Version | Install |
| --- | --- | --- |
| Python | 3.12 (pinned in `.python-version`) | `brew install python@3.12` |
| uv | 0.13+ | `brew install uv` |
| Node.js / npm | 26.x / 11.x | `brew install node` |
| libomp | latest | `brew install libomp` (needed by LightGBM) |
| Databricks CLI | 1.24+ | `brew tap databricks/tap && brew install databricks` |

## Install

```sh
scripts/setup.sh
```

This runs `uv sync --frozen` (exact versions from `uv.lock`), `npm ci` (exact versions from
`frontend/package-lock.json`), and installs Playwright Chromium.

## Why Python 3.12
The system default `python3` may be newer than what ML wheels (LightGBM, OR-Tools, MLflow) support.
Databricks Runtime 16.4+/17.x and serverless also run Python 3.12, which keeps Databricks Connect compatible in Phase 2.

## VS Code
Open the repo folder; accept the recommended extensions (`.vscode/extensions.json`). The interpreter is
`.venv/bin/python`. Formatting: Ruff for Python, Prettier for TypeScript.

## Frontend stack
React 19, TypeScript 7, Vite 8, Tailwind CSS v4 (via `@tailwindcss/vite`; no `tailwind.config.js` or PostCSS
config needed), React Router, TanStack Query, Zustand, ECharts (`echarts-for-react`), React Flow (`@xyflow/react`),
Motion, Lucide, Zod, Axios. Tests: Vitest + React Testing Library (jsdom), Playwright (Chromium). Linting: oxlint.

## Coding-agent skills
Project-scoped skills live in `.claude/skills/` (Claude Code):
- 14 Databricks skills from `databricks aitools install` (source: github.com/databricks/databricks-agent-skills, v0.2.32)
- `mlflow-trace-instrumentation`, `mlflow-evaluation` (shipped inside the `mlflow` package)

Refresh Databricks skills with `databricks aitools update`.
