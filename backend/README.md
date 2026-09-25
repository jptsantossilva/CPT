# Backend (FastAPI)

Install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Run:

```bash
uvicorn backend.app.main:app --reload --factory --host 127.0.0.1 --port 8000
```

Run tests:

```bash
pytest -q backend/tests
```

Required environment variable:

- `ENCRYPTION_KEY` (Fernet): used by the backend to encrypt/decrypt sensitive credentials (Binance, OKX, and Kraken API keys/secrets plus the OKX passphrase) before storing them in the database.
- Generate one with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Production container notes

- Backend Docker image: `backend/Dockerfile`
- Entrypoint: `backend/scripts/entrypoint.sh`
  - runs `alembic upgrade head` only if `alembic.ini` exists
  - runs `init_db()` to ensure schema exists
  - starts uvicorn on `0.0.0.0:${PORT:-8000}`

Seed sample data:

```bash
python -m backend.scripts.seed
```

Trigger sync:

```bash
curl -X POST http://127.0.0.1:8000/sync
```

Exchange account administration:

- `GET/POST /admin/exchange-accounts/`
- `PUT/DELETE /admin/exchange-accounts/{id}`
- Legacy `/admin/binance-accounts` endpoints remain available.

Only read-only Spot/cash balances are requested. OKX keys need **Read**;
Kraken keys need **Funds permissions - Query**; Binance keys keep the existing
read-only permission. Empty credential values on updates retain the encrypted
values already stored.
