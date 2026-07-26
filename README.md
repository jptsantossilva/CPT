# Crypto Portfolio Tracker

Track your crypto portfolio across:
- Binance accounts/subaccounts
- Multi-chain wallets (EVM, Bitcoin, Solana)
- NFTs with valuation and filtering

## Stack

- Backend: FastAPI + SQLModel
- Frontend: React + Vite + TypeScript
- Database: PostgreSQL

## Recommended Installation (Docker)

This is the recommended path for VPS/production and the easiest way to run the full app.

### Prerequisites

- Docker Engine 24+
- Docker Compose plugin (`docker compose`)
- Install Docker from the official docs: https://docs.docker.com/engine/install/

### Quick Deploy on a VPS (without cloning the full repo)

If you only want to run the app quickly on a server:

```bash
mkdir -p cpt
cd cpt

curl -fsSL https://raw.githubusercontent.com/jptsantossilva/CPT/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/jptsantossilva/CPT/main/.env.example -o .env.example
```

### 1) Configure environment

Create your runtime `.env` from the template:

```bash
cp .env.example .env
```

Set at least:

```bash
POSTGRES_DB=cpt
POSTGRES_USER=cpt
POSTGRES_PASSWORD=<strong-password>
ENCRYPTION_KEY=<fernet-key>
```

Generate a Fernet key:

```bash
python3 - <<'PY'
import base64, os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
PY

```

Then fill the API/RPC variables you want to use (`BINANCE_*`, `ETH_RPC_URL`, `BASE_RPC_URL`, `POLYGON_RPC_URL`, `SOLANA_RPC_URL`, `OPENSEA_API_KEY`, etc.).

### 2) Start services

```bash
docker compose -f docker-compose.yml up -d
```

Services:
- `frontend` (nginx): exposed on `${APP_PORT:-80}`
- `backend` (FastAPI)
- `db` (Postgres with persistent volume `postgres_data`)

### 3) Verify application

```bash
docker compose -f docker-compose.yml ps
curl -s http://localhost/api/snapshot/latest
```

Open in browser:
- `http://<server-ip>:<APP_PORT>`

### 4) Update safely (with DB backup)

```bash
./scripts/update_prod.sh
```

This script:
1. creates a Postgres backup in `./backups`
2. pulls latest images
3. recreates containers

Optional local image build before restart:

```bash
BUILD_LOCAL=1 ./scripts/update_prod.sh
```

### Automatic Sync Schedule

In Admin, automatic sync supports only:
- `minutes`
- `hours`
- `days`
- `weeks`

Rules:
- `time_of_day` is always interpreted in **UTC**.
- For `minutes`: sync runs every N minutes.
- For `hours`: sync runs every N hours.
- For `days`: sync runs every N days at `time_of_day`.
- For `weeks`: sync runs every N weeks on `day_of_week` at `time_of_day`.

### Portfolio Notifications (Email / Telegram)

Backend now supports configurable notifications in Admin:
- one or more notification configs
- one or more recipients per config
- channel per config: `email` or `telegram`
- schedule mode: `inherit` (Automatic Sync Schedule) or `custom`

Main admin endpoints:
- `GET /admin/notifications/`
- `POST /admin/notifications/`
- `PUT /admin/notifications/{id}`
- `PUT /admin/notifications/{id}/recipients`
- `GET /admin/notifications/{id}/preview`
- `POST /admin/notifications/{id}/run`

Message includes:
- total portfolio value
- variation vs last successful notification
- global PnL and percentage return on net invested capital when FIAT cash flows establish a valid baseline
- top 5 movers up and top 5 movers down (coins + NFTs)

Detailed technical design:
- `backend/README_NOTIFICATIONS.md`

### FIAT Investments and Portfolio PnL

The **Investments** page records FIAT added to or withdrawn from the tracked
crypto portfolio. Each movement stores its date, original EUR/USD amount, the
historical equivalent in the other currency, and the bank or person associated
with it.

The dashboard uses the latest valid portfolio snapshot and calculates, in the
selected currency:

- `Net invested = FIAT added - FIAT withdrawn`
- `Global PnL = current portfolio + FIAT withdrawn - FIAT added`
- `Global PnL % = Global PnL / net invested capital × 100`

When no withdrawals exist, global PnL is entirely unrealized and is labelled
**Unrealized PnL**. Once a withdrawal exists, the app labels it **Global PnL**:
realized and unrealized PnL cannot be separated without the cost basis of the
assets sold.

The percentage is unavailable if net invested capital is zero or negative,
because it would not represent a meaningful return percentage.

Cash flows dated after the latest snapshot are shown as pending and excluded
from PnL until another sync is completed. Banks and people are cash-flow
labels only; the app does not allocate portfolio ownership or PnL to them.

Main endpoints:

- `GET/POST /admin/fiat-cashflows/`
- `PUT/DELETE /admin/fiat-cashflows/{id}`
- `GET /portfolio/performance`



## Local Development (optional)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Disclaimer

This software is for educational purposes only.

Use this software at your own risk. The authors and affiliates assume no responsibility for financial decisions made using this data.

Portfolio values, prices, balances, and NFT valuations may be delayed, incomplete, or inaccurate depending on third-party APIs.

This software does not execute trades and should not be considered investment advice.

There may be bugs in the code. This software is provided without any warranty.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
