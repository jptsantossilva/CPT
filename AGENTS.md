# CPT Agent Guide

## Project Overview
CPT is a Crypto Portfolio Tracker for monitoring Binance accounts/subaccounts,
multi-chain wallets, NFTs, portfolio history, sync scheduling, and email/Telegram
notifications. The backend is FastAPI + SQLModel, the frontend is React + Vite +
TypeScript, and production uses PostgreSQL through Docker Compose.

Keep this file brief and focused. Put longer task-specific guidance in
project documentation such as `README.md`, `backend/README.md`, or
`backend/README_NOTIFICATIONS.md`.

## Repository Layout
- `backend/app/` contains the FastAPI application, database layer, models, APIs,
  and service modules.
- `backend/app/services/` contains integrations and business logic for Binance,
  wallets, prices, NFTs, scheduler, notifications, and portfolio history.
- `backend/app/api/` contains admin and wallet API routers.
- `backend/tests/` contains Python tests for backend services and API behavior.
- `backend/scripts/` contains helper scripts such as manual sync and seed data.
- `frontend/src/` contains the React UI pages, shared API client, theme, and app
  shell.
- `frontend/` contains Vite, TypeScript, nginx, and frontend Docker config.
- `docker-compose.yml`, `backend/Dockerfile`, and `frontend/Dockerfile` define
  container runtime.
- Runtime files such as `.env`, `dev.db`, `frontend/dist/`, `frontend/node_modules/`,
  and generated backups are local state, not source code.

## Setup and Commands
- A local Python virtual environment may exist at `.venv/`; prefer
  `.venv/bin/python`, `.venv/bin/pytest`, and `.venv/bin/uvicorn` when available.
- Install backend dependencies: `python -m pip install -r backend/requirements.txt`
- Run backend locally:
  `uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000`
- Trigger a manual sync script: `python backend/scripts/sync_now.py`
- Install frontend dependencies: `cd frontend && npm install`
- Run frontend locally: `cd frontend && npm run dev`
- Build frontend: `cd frontend && npm run build`
- Start Docker stack: `docker compose up -d`
- Inspect Docker logs:
  `docker compose logs -f backend`, `docker compose logs -f frontend`, or
  `docker compose logs -f db`
- Update production safely: `./scripts/update_prod.sh`

## Testing and Validation
- Run backend tests: `.venv/bin/pytest backend/tests` when `.venv/` exists, or
  `python -m pytest backend/tests`.
- Run targeted backend tests for touched services, for example
  `.venv/bin/pytest backend/tests/test_sync_calc.py`.
- Compile Python files after backend edits when tests are not enough:
  `.venv/bin/python -m py_compile backend/app/**/*.py backend/scripts/*.py`
- For frontend changes, run `cd frontend && npm run build`.
- For API or scheduler changes, run the relevant backend tests and manually check
  `/health`, `/sync/status`, or the affected endpoint when practical.
- For Docker/runtime changes, verify the relevant service starts and logs cleanly.

## Portfolio and Data Safety Rules
- Never commit `.env`, API keys, Binance credentials, Telegram tokens, email
  passwords, encryption keys, Postgres dumps, `dev.db`, or other local runtime
  secrets/state.
- Do not run `docker compose down -v` unless the user explicitly asks to delete
  persistent production data.
- Treat balance syncing, price mapping, NFT valuation, notification dispatch,
  scheduler timing, database persistence, and currency conversion as high-risk
  behavior. Add focused tests or a clear manual validation note when changing
  these areas.
- This project does not execute trades. Do not add trading/order execution
  behavior unless the user explicitly requests it and the risk is discussed first.
- Be careful with symbol-only price lookups. Crypto tickers can be ambiguous;
  use explicit provider IDs or overrides for known ambiguous assets.
- Preserve production update and deployment compatibility unless intentionally
  changing Docker, GitHub image publishing, or VPS update behavior.

## Documentation Workflow
- Keep `README.md` installation, Docker, and production update commands aligned
  with `docker-compose.yml` and `scripts/update_prod.sh`.
- Keep notification behavior documentation aligned with
  `backend/README_NOTIFICATIONS.md`.
- Update `CHANGELOG.md` for user-visible behavior changes, production fixes,
  deployment changes, and notable agent-context updates.
- Add screenshots or generated reports only when they are intentionally part of
  project documentation.

## Known Gotchas
- Production uses PostgreSQL, while local development may use `dev.db` depending
  on environment variables. Confirm `DATABASE_URL` before debugging data issues.
- Price and icon data are cached in memory in `backend/app/services/prices.py`;
  stale values may remain until cache expiry or process restart.
- Historical snapshots are persisted records. Fixing a price mapping affects new
  syncs, but existing snapshots are not recalculated automatically.
- Automatic sync `time_of_day` is interpreted in UTC.
- API integrations may fail because of third-party rate limits, missing RPC URLs,
  unavailable APIs, or absent optional API keys. Surface these as degraded data
  rather than silently changing semantics.
- Frontend currency display follows the app currency setting and may differ from
  backend storage, which keeps both EUR and USD values.

## Task-Specific Docs
- Use `backend/README.md` for backend setup details.
- Use `frontend/README.md` for frontend/Vite details.
- Use `backend/README_NOTIFICATIONS.md` for notification design and behavior.
- Use `README.md` for production Docker deployment, update flow, and user-facing
  limitations.
