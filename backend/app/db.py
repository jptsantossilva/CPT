import os

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .models import Account, AppSetting, Holding, NFTBlacklist, NFTHolding, Price, Snapshot
from .wallet_chains import parse_wallet_identifier

DB_URL = os.getenv("DATABASE_URL") or settings.DATABASE_URL
engine = create_engine(DB_URL, echo=False)


def init_db():
    SQLModel.metadata.create_all(engine)
    _ensure_nft_holding_columns()


def _ensure_nft_holding_columns() -> None:
    """Best-effort schema compatibility for existing databases."""
    try:
        insp = inspect(engine)
        if "nftholding" not in insp.get_table_names():
            return
        existing = {str(c.get("name")) for c in insp.get_columns("nftholding")}
        stmts: list[str] = []
        if "is_spam" not in existing:
            stmts.append("ALTER TABLE nftholding ADD COLUMN is_spam BOOLEAN DEFAULT 0")
        if "has_floor_or_last_sale" not in existing:
            stmts.append("ALTER TABLE nftholding ADD COLUMN has_floor_or_last_sale BOOLEAN DEFAULT 0")
        if "visibility" not in existing:
            stmts.append("ALTER TABLE nftholding ADD COLUMN visibility VARCHAR DEFAULT 'visible'")
        if "valuation_source" not in existing:
            stmts.append("ALTER TABLE nftholding ADD COLUMN valuation_source VARCHAR")
        if "valuation_confidence" not in existing:
            stmts.append("ALTER TABLE nftholding ADD COLUMN valuation_confidence VARCHAR")
        if not stmts:
            return
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(text(stmt))
    except Exception:
        # Keep startup resilient; sync/list APIs can still operate with defaults.
        return


def get_session():
    return Session(engine)


def get_latest_snapshot():
    with get_session() as s:
        q = select(Snapshot).order_by(Snapshot.timestamp.desc()).limit(1)
        res = s.exec(q).first()
        return res


def get_app_setting(key: str) -> str | None:
    with get_session() as s:
        row = s.get(AppSetting, key)
        return row.value if row else None


def set_app_setting(key: str, value: str) -> None:
    with get_session() as s:
        row = s.get(AppSetting, key)
        if row:
            row.value = value
            s.add(row)
        else:
            s.add(AppSetting(key=key, value=value))
        s.commit()


def list_assets():
    with get_session() as s:
        holdings = s.exec(select(Holding)).all()
        if not holdings:
            return []

        accounts = s.exec(select(Account)).all()
        account_by_id: dict[int, Account] = {a.id: a for a in accounts if a.id is not None}

        prices = s.exec(select(Price).order_by(Price.ts.desc())).all()
        latest_price_by_symbol: dict[str, Price] = {}
        for p in prices:
            sym = (p.asset_symbol or "").upper()
            if sym and sym not in latest_price_by_symbol:
                latest_price_by_symbol[sym] = p

        out = []
        for h in holdings:
            sym = (h.asset_symbol or "").upper()
            if not sym:
                continue
            price = latest_price_by_symbol.get(sym)
            price_eur = float(price.price_eur) if price else 0.0
            price_usd = float(price.price_usd) if price and price.price_usd else 0.0
            qty = float(h.quantity or 0.0)
            account_id = int(h.account_id)
            account = account_by_id.get(account_id)
            account_label = account.label if account and account.label else None
            account_identifier = account.identifier if account and account.identifier else None
            if account and account.provider == "wallet":
                chain, wallet_identifier = parse_wallet_identifier(account.identifier)
                if wallet_identifier:
                    account_identifier = (
                        wallet_identifier if chain == "ethereum" else f"{chain}:{wallet_identifier}"
                    )
            holding_chain = (h.asset_name or "").strip().lower() or None
            out.append(
                {
                    "id": int(h.id) if h.id is not None else None,
                    "asset_symbol": sym,
                    "account_id": account_id,
                    "account_identifier": account_identifier,
                    "account_label": account_label,
                    "account_display": account_label or account_identifier or "unknown",
                    "chain": holding_chain,
                    "quantity": qty,
                    "price_eur": price_eur,
                    "price_usd": price_usd,
                    "value_eur": qty * price_eur,
                    "value_usd": qty * price_usd,
                }
            )

        return out


def list_nfts(include_hidden: bool = False):
    with get_session() as s:
        rows = s.exec(select(NFTHolding)).all()
        if not rows:
            return []

        accounts = s.exec(select(Account)).all()
        account_by_id: dict[int, Account] = {a.id: a for a in accounts if a.id is not None}
        prices = s.exec(select(Price).order_by(Price.ts.desc())).all()
        latest_price_by_symbol: dict[str, Price] = {}
        for p in prices:
            sym = (p.asset_symbol or "").upper()
            if sym and sym not in latest_price_by_symbol:
                latest_price_by_symbol[sym] = p

        out = []
        for row in rows:
            account = account_by_id.get(int(row.account_id))
            account_label = account.label if account and account.label else None
            account_identifier = account.identifier if account and account.identifier else None
            if account and account.provider == "wallet":
                _, wallet_identifier = parse_wallet_identifier(account.identifier)
                if wallet_identifier:
                    account_identifier = wallet_identifier
            valuation_symbol = str(row.valuation_symbol or "").upper()
            valuation_native = float(row.valuation_native or 0)
            valuation_usd = float(row.valuation_usd or 0)
            valuation_eur = float(row.valuation_eur or 0)
            price = latest_price_by_symbol.get(valuation_symbol)
            if price and valuation_native:
                valuation_usd = valuation_native * float(price.price_usd or 0)
                valuation_eur = valuation_native * float(price.price_eur or 0)
            visibility = (getattr(row, "visibility", None) or "visible").strip().lower()
            if visibility not in {"visible", "hidden"}:
                visibility = "visible"
            if not include_hidden and visibility == "hidden":
                continue
            out.append(
                {
                    "id": int(row.id) if row.id is not None else None,
                    "account_id": int(row.account_id),
                    "account_label": account_label,
                    "account_identifier": account_identifier,
                    "account_display": account_label or account_identifier or "unknown",
                    "chain": (row.chain or "").lower(),
                    "contract": row.contract,
                    "token_id": row.token_id,
                    "name": row.name,
                    "collection": row.collection,
                    "owner": row.owner,
                    "valuation_symbol": valuation_symbol,
                    "valuation_native": valuation_native,
                    "valuation_usd": valuation_usd,
                    "valuation_eur": valuation_eur,
                    # Strict ETH value: only when primary valuation is already in ETH.
                    "valuation_eth": valuation_native if valuation_symbol == "ETH" else None,
                    "valuation_source": getattr(row, "valuation_source", None),
                    "valuation_confidence": getattr(row, "valuation_confidence", None),
                    "is_spam": bool(getattr(row, "is_spam", False)),
                    "has_floor_or_last_sale": bool(getattr(row, "has_floor_or_last_sale", False)),
                    "visibility": visibility,
                }
            )
        return out


def get_nft_blacklist_keys() -> set[tuple[str, str, str]]:
    with get_session() as s:
        rows = s.exec(select(NFTBlacklist)).all()
        out: set[tuple[str, str, str]] = set()
        for r in rows:
            chain = (r.chain or "").strip().lower()
            contract = (r.contract or "").strip().lower()
            token_id = str(r.token_id or "").strip()
            if chain and contract and token_id:
                out.add((chain, contract, token_id))
        return out


def set_nft_visibility(nft_id: int, visibility: str) -> dict:
    vis = (visibility or "").strip().lower()
    if vis not in {"visible", "hidden"}:
        raise ValueError("visibility must be 'visible' or 'hidden'")

    with get_session() as s:
        row = s.get(NFTHolding, nft_id)
        if not row:
            raise KeyError("nft not found")

        row.visibility = vis
        chain = (row.chain or "").strip().lower()
        contract = (row.contract or "").strip().lower()
        token_id = str(row.token_id or "").strip()

        if chain and contract and token_id:
            existing = s.exec(
                select(NFTBlacklist).where(
                    NFTBlacklist.chain == chain,
                    NFTBlacklist.contract == contract,
                    NFTBlacklist.token_id == token_id,
                )
            ).first()
            if vis == "hidden":
                if not existing:
                    s.add(
                        NFTBlacklist(
                            chain=chain,
                            contract=contract,
                            token_id=token_id,
                            reason="manual_hidden",
                        )
                    )
            else:
                if existing:
                    s.delete(existing)

        s.add(row)
        s.commit()
        s.refresh(row)
        return {
            "id": int(row.id) if row.id is not None else None,
            "visibility": row.visibility,
            "chain": row.chain,
            "contract": row.contract,
            "token_id": row.token_id,
        }
