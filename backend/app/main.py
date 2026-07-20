from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import select

from . import db, services
from .api import binance_accounts, notifications, price_mappings, snapshots, sync_schedule, wallets
from .models import Snapshot

app = FastAPI(title="Crypto Portfolio Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    db.init_db()
    services.scheduler.start()
    services.notifications.start()


@app.on_event("shutdown")
def on_shutdown():
    services.notifications.stop()
    services.scheduler.stop()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sync")
async def sync(background_tasks: BackgroundTasks):
    """Trigger an immediate sync. The backend runs sync in background."""
    if services.sync.is_sync_running():
        return {"status": "already_running", "sync": services.sync.get_sync_status()}
    background_tasks.add_task(services.sync.sync_all, "manual")
    return {"status": "sync_started", "sync": services.sync.get_sync_status()}


@app.get("/sync/status")
def sync_status():
    return services.sync.get_sync_status()


@app.get("/snapshot/latest")
def latest_snapshot():
    snap = db.get_latest_snapshot()
    if not snap:
        raise HTTPException(status_code=404, detail="no snapshot")
    return snap


@app.get("/snapshot/history")
def snapshot_history(limit: int = 400):
    n = max(1, min(int(limit or 400), 5000))
    with db.get_session() as s:
        rows = s.exec(
            select(Snapshot)
            .where(Snapshot.is_valid == True)  # noqa: E712
            .order_by(Snapshot.timestamp.asc())
            .limit(n)
        ).all()
    return rows


@app.get("/snapshot/variations")
def snapshot_variations():
    with db.get_session() as s:
        rows = s.exec(
            select(Snapshot).where(Snapshot.is_valid == True).order_by(Snapshot.timestamp.asc())  # noqa: E712
        ).all()
    return services.history.compute_variations(rows)


@app.get("/history/portfolio")
def portfolio_history(limit: int = 800):
    n = max(1, min(int(limit or 800), 5000))
    with db.get_session() as s:
        rows = s.exec(
            select(Snapshot)
            .where(Snapshot.is_valid == True)  # noqa: E712
            .order_by(Snapshot.timestamp.asc())
            .limit(n)
        ).all()
    return services.history.build_portfolio_history(rows)


@app.get("/assets")
def assets(include_hidden: bool = False):
    return db.list_assets(include_hidden=include_hidden)


@app.get("/assets/icons")
def asset_icons(symbols: str = ""):
    # Accept comma-separated symbols from frontend.
    items = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not items:
        return {}
    return services.prices.fetch_icon_urls(items)


@app.get("/nfts")
def nfts(include_hidden: bool = False):
    return db.list_nfts(include_hidden=include_hidden)


class NftVisibilityUpdate(BaseModel):
    visibility: str


class CurrencySettingUpdate(BaseModel):
    currency: str


@app.put("/nfts/{nft_id}/visibility")
def update_nft_visibility(nft_id: int, payload: NftVisibilityUpdate):
    try:
        return db.set_nft_visibility(nft_id, payload.visibility)
    except KeyError:
        raise HTTPException(status_code=404, detail="nft not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/settings/currency")
def get_currency_setting():
    return {"currency": services.notifications.get_notification_currency()}


@app.put("/settings/currency")
def update_currency_setting(payload: CurrencySettingUpdate):
    try:
        return {"currency": services.notifications.set_notification_currency(payload.currency)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# admin routes
app.include_router(binance_accounts.router)
app.include_router(wallets.router)
app.include_router(sync_schedule.router)
app.include_router(notifications.router)
app.include_router(price_mappings.router)
app.include_router(snapshots.router)
