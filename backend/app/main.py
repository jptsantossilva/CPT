from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, services
from .api import binance_accounts, wallets

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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sync")
async def sync(background_tasks: BackgroundTasks):
    """Trigger an immediate sync. The backend runs sync in background."""
    if services.sync.is_sync_running():
        return {"status": "already_running", "sync": services.sync.get_sync_status()}
    background_tasks.add_task(services.sync.sync_all)
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


@app.get("/assets")
def assets():
    return db.list_assets()


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


@app.put("/nfts/{nft_id}/visibility")
def update_nft_visibility(nft_id: int, payload: NftVisibilityUpdate):
    try:
        return db.set_nft_visibility(nft_id, payload.visibility)
    except KeyError:
        raise HTTPException(status_code=404, detail="nft not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# admin routes
app.include_router(binance_accounts.router)
app.include_router(wallets.router)
