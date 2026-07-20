import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import Lock

from ..db import get_session
from ..models import Account, Holding, NFTHolding, Price, Snapshot
from ..wallet_chains import parse_wallet_identifier
from . import binance, btc, eth, nfts, prices, solana

log = logging.getLogger(__name__)

_EVM_NATIVE_SYMBOLS = {
    "ethereum": "ETH",
    "base": "ETH",
    "polygon": "POL",
}

_state_lock = Lock()
_sync_state: dict[str, object] = {
    "status": "idle",
    "progress": 0,
    "message": "idle",
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "warning": None,
    "holdings_count": None,
    "nfts_count": None,
    "total_eur": None,
    "total_usd": None,
}


def _sync_max_workers() -> int:
    raw = os.getenv("SYNC_MAX_WORKERS", "6").strip()
    try:
        n = int(raw)
    except Exception:
        n = 6
    return max(1, min(16, n))


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _set_state(
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    last_error: str | None = None,
    warning: str | None = None,
    holdings_count: int | None = None,
    nfts_count: int | None = None,
    total_eur: float | None = None,
    total_usd: float | None = None,
) -> None:
    with _state_lock:
        if status is not None:
            _sync_state["status"] = status
        if progress is not None:
            _sync_state["progress"] = progress
        if message is not None:
            _sync_state["message"] = message
        if started_at is not None:
            _sync_state["started_at"] = started_at
        if finished_at is not None:
            _sync_state["finished_at"] = finished_at
        _sync_state["last_error"] = last_error
        _sync_state["warning"] = warning
        _sync_state["holdings_count"] = holdings_count
        _sync_state["nfts_count"] = nfts_count
        _sync_state["total_eur"] = total_eur
        _sync_state["total_usd"] = total_usd


def _wallet_rpc_warning() -> str | None:
    try:
        with get_session() as s:
            rows = s.query(Account).filter(Account.provider == "wallet").all()
            if not rows:
                return None
            evm_wallet_exists = any(
                parse_wallet_identifier(a.identifier)[0] in {"ethereum", "base", "polygon"}
                for a in rows
            )
            if not evm_wallet_exists:
                return None
            missing_chains = [c for c in ("ethereum", "base", "polygon") if not eth.rpc_url_for_chain(c)]
            if missing_chains:
                missing_txt = ", ".join(missing_chains)
                return (
                    f"Wallet RPC URL missing for chain(s): {missing_txt}. "
                    "Wallet balances on those chains are not being synced."
                )
    except Exception:
        log.exception("failed checking wallet RPC warning status")
    return None


def get_sync_status() -> dict[str, object]:
    with _state_lock:
        out = dict(_sync_state)
    # Dynamic warning so dashboard can show this even before running a sync.
    if not out.get("warning"):
        out["warning"] = _wallet_rpc_warning()
    return out


def is_sync_running() -> bool:
    with _state_lock:
        return _sync_state.get("status") == "running"


def _symbol_price_key(symbol: str) -> str:
    return f"symbol:{str(symbol or '').strip().upper()}"


def _aggregate_holdings(rows: list[dict]) -> list[dict]:
    """Combine duplicate account/asset identities without collapsing contracts."""
    combined: dict[tuple[int, str], dict] = {}
    for row in rows:
        account_id = int(row.get("account_id") or 0)
        asset_key = str(row.get("asset_key") or "").strip()
        if not account_id or not asset_key:
            continue
        key = (account_id, asset_key)
        existing = combined.get(key)
        if existing is None:
            combined[key] = dict(row)
            continue
        existing["qty"] = float(existing.get("qty") or 0.0) + float(row.get("qty") or 0.0)
        if str(row.get("visibility") or "visible").lower() == "hidden":
            existing["visibility"] = "hidden"
            existing["risk_reason"] = row.get("risk_reason") or existing.get("risk_reason")
    return list(combined.values())


def _sync_binance_accounts() -> list[dict]:
    return _sync_binance_accounts_with_rows()


def _sync_binance_accounts_with_rows(
    rows: list[Account] | None = None,
    on_progress=None,
) -> list[dict]:
    totals: list[dict] = []
    if rows is None:
        with get_session() as s:
            rows = s.query(Account).filter(Account.provider == "binance").all()
        include_subaccounts = len(rows) == 1
        if not include_subaccounts:
            log.info(
                "multiple Binance accounts configured (%s): disabling subaccount merge per account to avoid duplicates",
                len(rows),
            )
    include_subaccounts = len(rows) == 1
    if not include_subaccounts and rows:
        log.info(
            "multiple Binance accounts configured (%s): disabling subaccount merge per account to avoid duplicates",
            len(rows),
        )
    for idx, a in enumerate(rows):
        if on_progress:
            on_progress(idx, len(rows), a)
        try:
            balances = binance.fetch_balances_for_account(
                a,
                include_subaccounts=include_subaccounts,
            )
        except Exception:
            log.exception("failed to fetch Binance balances for account_id=%s", a.id)
            continue

        for b in balances:
            asset = b.get("asset")
            if not asset:
                continue
            free = float(b.get("free", 0) or 0)
            locked = float(b.get("locked", 0) or 0)
            qty = free + locked
            if qty <= 0:
                continue
            symbol = str(asset).strip().upper()
            totals.append(
                {
                    "account_id": a.id,
                    "asset": symbol,
                    "qty": qty,
                    "asset_key": _symbol_price_key(symbol),
                    "price_key": _symbol_price_key(symbol),
                    "asset_kind": None,
                    "contract_address": None,
                    "visibility": "visible",
                    "risk_reason": None,
                }
            )
    return totals


def _sync_wallet_accounts() -> list[dict]:
    return _sync_wallet_accounts_with_rows()


def _sync_wallet_accounts_with_rows(
    rows: list[Account] | None = None,
    on_progress=None,
) -> list[dict]:
    totals: list[dict] = []
    if rows is None:
        with get_session() as s:
            rows = s.query(Account).filter(Account.provider == "wallet").all()

    def _fetch_for_wallet(a: Account) -> list[dict]:
        out: list[dict] = []
        chain_hint, address = parse_wallet_identifier(a.identifier)

        if chain_hint == "bitcoin":
            try:
                balances = btc.fetch_wallet_balances(address)
            except Exception:
                log.exception("failed to fetch BTC wallet balances for account_id=%s", a.id)
                balances = []
            for b in balances:
                asset = (b.get("symbol") or b.get("asset") or "").strip().upper()
                if not asset:
                    continue
                qty = float(b.get("balance", 0) or 0)
                if qty <= 0:
                    continue
                out.append(
                    {
                        "account_id": a.id,
                        "asset": asset,
                        "qty": qty,
                        "chain": "bitcoin",
                        "asset_key": f"native:bitcoin:{asset}",
                        "price_key": _symbol_price_key(asset),
                        "asset_kind": "native",
                        "contract_address": None,
                        "visibility": "visible",
                        "risk_reason": None,
                    }
                )
            return out
        if chain_hint == "solana":
            try:
                balances = solana.fetch_wallet_balances(address)
            except Exception:
                log.exception("failed to fetch SOL wallet balances for account_id=%s", a.id)
                balances = []
            for b in balances:
                # Keep Solana symbols/mints as provided by the service.
                # Uppercasing can corrupt base58 mint values.
                asset = (b.get("symbol") or b.get("asset") or "").strip()
                if not asset:
                    continue
                qty = float(b.get("balance", 0) or 0)
                if qty <= 0:
                    continue
                out.append(
                    {
                        "account_id": a.id,
                        "asset": asset,
                        "qty": qty,
                        "chain": "solana",
                        "asset_key": f"symbol:{asset}",
                        "price_key": _symbol_price_key(asset),
                        "asset_kind": None,
                        "contract_address": None,
                        "visibility": "visible",
                        "risk_reason": None,
                    }
                )
            return out

        for chain in ("ethereum", "base", "polygon"):
            try:
                balances = eth.fetch_wallet_balances(address, chain=chain)
            except Exception:
                log.exception(
                    "failed to fetch wallet balances for account_id=%s chain=%s",
                    a.id,
                    chain,
                )
                continue

            for b in balances:
                asset = (b.get("symbol") or b.get("asset") or "").strip().upper()
                if not asset:
                    continue
                qty = float(b.get("balance", 0) or 0)
                if qty <= 0:
                    continue
                native_symbol = _EVM_NATIVE_SYMBOLS[chain]
                raw_kind = str(b.get("asset_kind") or "").strip().lower()
                contract = str(b.get("contract") or "").strip().lower()
                if raw_kind == "native" or contract == "native":
                    asset_kind = "native"
                    contract_address = None
                elif raw_kind == "erc20" or contract:
                    asset_kind = "erc20"
                    contract_address = contract or None
                elif asset == native_symbol:
                    # Compatibility with custom/test providers that predate
                    # explicit asset_kind metadata.
                    asset_kind = "native"
                    contract_address = None
                else:
                    asset_kind = "erc20"
                    contract_address = None

                if asset_kind == "native":
                    asset_key = f"native:{chain}:{asset}"
                    price_key = _symbol_price_key(asset)
                    visibility = "visible"
                    risk_reason = None
                else:
                    identity_contract = contract_address or f"unknown:{asset}"
                    asset_key = f"erc20:{chain}:{identity_contract}"
                    price_key = asset_key
                    suspicious = asset == native_symbol
                    visibility = "hidden" if suspicious else "visible"
                    risk_reason = "reserved_native_symbol" if suspicious else None
                out.append(
                    {
                        "account_id": a.id,
                        "asset": asset,
                        "qty": qty,
                        "chain": chain,
                        "asset_key": asset_key,
                        "price_key": price_key,
                        "asset_kind": asset_kind,
                        "contract_address": contract_address,
                        "visibility": visibility,
                        "risk_reason": risk_reason,
                    }
                )
        return out

    if not rows:
        return totals

    max_workers = min(_sync_max_workers(), len(rows))
    if max_workers <= 1:
        for idx, a in enumerate(rows):
            if on_progress:
                on_progress(idx, len(rows), a)
            totals.extend(_fetch_for_wallet(a))
        return _aggregate_holdings(totals)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_for_wallet, a): a for a in rows}
        done = 0
        for fut in as_completed(futures):
            a = futures[fut]
            done += 1
            if on_progress:
                on_progress(done - 1, len(rows), a)
            try:
                totals.extend(fut.result())
            except Exception:
                log.exception("failed to fetch wallet balances for account_id=%s", a.id)
    return _aggregate_holdings(totals)


def _apply_nft_blacklist(
    rows: list[dict],
    blacklist_keys: set[tuple[str, str, str]],
) -> list[dict]:
    if not blacklist_keys:
        return rows
    out: list[dict] = []
    for row in rows:
        chain = str(row.get("chain") or "").strip().lower()
        contract = str(row.get("contract") or "").strip().lower()
        token_id = str(row.get("token_id") or "").strip()
        if (chain, contract, token_id) in blacklist_keys:
            patched = dict(row)
            patched["visibility"] = "hidden"
            out.append(patched)
        else:
            out.append(row)
    return out


def _persist_daily_snapshot(
    session,
    *,
    total_eur: float,
    total_usd: float,
    holdings_count: int,
    symbols_count: int,
    nfts_count: int = 0,
    meta_payload: dict | None = None,
) -> None:
    now_utc = datetime.utcnow()
    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    session.query(Snapshot).filter(Snapshot.timestamp >= day_start, Snapshot.timestamp < day_end).delete(
        synchronize_session=False
    )
    meta = {
        "holdings_count": holdings_count,
        "symbols_count": symbols_count,
        "nfts_count": nfts_count,
    }
    if meta_payload:
        meta.update(meta_payload)
    session.add(
        Snapshot(
            total_eur=total_eur,
            total_usd=total_usd,
            meta=json.dumps(meta),
        )
    )


def sync_all(trigger: str = "manual") -> None:
    """Fetch holdings, prices, and persist both holdings and snapshot totals."""
    trigger_mode = str(trigger or "manual").strip().lower()
    if trigger_mode not in {"manual", "auto"}:
        trigger_mode = "manual"
    started = _utc_now_iso()
    _set_state(
        status="running",
        progress=2,
        message="Preparing sync...",
        started_at=started,
        finished_at=None,
        last_error=None,
        warning=None,
        holdings_count=None,
        nfts_count=None,
        total_eur=None,
        total_usd=None,
    )

    try:
        with get_session() as s:
            binance_rows = s.query(Account).filter(Account.provider == "binance").all()
            wallet_rows = s.query(Account).filter(Account.provider == "wallet").all()

        def _fmt_account(a: Account) -> str:
            return a.label or a.identifier or f"id={a.id}"

        def _b_progress(i: int, total: int, a: Account) -> None:
            if total <= 0:
                return
            pct = 5 + int(((i + 1) / total) * 35)
            _set_state(
                progress=min(pct, 40),
                message=f"Fetching Binance balances ({i + 1}/{total}): {_fmt_account(a)}",
            )

        def _w_progress(i: int, total: int, a: Account) -> None:
            if total <= 0:
                return
            pct = 40 + int(((i + 1) / total) * 35)
            _set_state(
                progress=min(pct, 75),
                message=f"Fetching wallet balances ({i + 1}/{total}): {_fmt_account(a)}",
            )

        _set_state(progress=5, message=f"Starting Binance sync for {len(binance_rows)} account(s)...")
        holdings = _sync_binance_accounts_with_rows(binance_rows, on_progress=_b_progress)
        _set_state(progress=40, message=f"Starting wallet sync for {len(wallet_rows)} wallet(s)...")
        wallet_holdings = _sync_wallet_accounts_with_rows(wallet_rows, on_progress=_w_progress)
        holdings.extend(wallet_holdings)
        holdings = _aggregate_holdings(holdings)
        _set_state(progress=76, message=f"Fetching NFTs for {len(wallet_rows)} wallet(s)...")
        synced_nfts: list[dict] = []

        def _fetch_nfts_for_wallet_account(a: Account) -> list[dict]:
            chain_hint, address = parse_wallet_identifier(a.identifier)
            if chain_hint in {"bitcoin", "solana"}:
                return []
            out: list[dict] = []
            wallet_nfts = nfts.fetch_nfts_for_wallet(address)
            for item in wallet_nfts:
                row = dict(item)
                row["account_id"] = int(a.id) if a.id is not None else 0
                out.append(row)
            return out

        if wallet_rows:
            max_workers = min(_sync_max_workers(), len(wallet_rows))
            if max_workers <= 1:
                for a in wallet_rows:
                    try:
                        synced_nfts.extend(_fetch_nfts_for_wallet_account(a))
                    except Exception:
                        log.exception("failed to fetch NFTs for wallet account_id=%s", a.id)
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = {ex.submit(_fetch_nfts_for_wallet_account, a): a for a in wallet_rows}
                    for fut in as_completed(futures):
                        a = futures[fut]
                        try:
                            synced_nfts.extend(fut.result())
                        except Exception:
                            log.exception("failed to fetch NFTs for wallet account_id=%s", a.id)
        blacklist_keys = set()
        try:
            from .. import db as db_module

            blacklist_keys = db_module.get_nft_blacklist_keys()
        except Exception:
            log.exception("failed loading NFT blacklist")
        if blacklist_keys:
            synced_nfts = _apply_nft_blacklist(synced_nfts, blacklist_keys)
        warning_parts = [message for message in (_wallet_rpc_warning(),) if message]
        visible_holdings = [
            h for h in holdings if str(h.get("visibility") or "visible").strip().lower() == "visible"
        ]
        hidden_holdings_count = len(holdings) - len(visible_holdings)
        _set_state(
            progress=78,
            message=(
                f"{len(visible_holdings)} visible holdings, {hidden_holdings_count} suspicious hidden, "
                f"and {len(synced_nfts)} NFTs collected"
            ),
        )

        symbol_holdings = [h for h in visible_holdings if h.get("asset_kind") != "erc20"]
        contract_holdings = [h for h in visible_holdings if h.get("asset_kind") == "erc20"]
        symbols = sorted({str(h["asset"]) for h in symbol_holdings})
        _set_state(progress=84, message=f"Fetching prices for {len(visible_holdings)} assets...")
        symbol_prices = prices.fetch_prices(symbols)
        price_map: dict[str, dict] = {
            _symbol_price_key(sym): data for sym, data in symbol_prices.items()
        }
        contract_prices = prices.fetch_evm_token_prices(contract_holdings)
        price_map.update(contract_prices)
        if any(str(p.get("source") or "") == "coingecko_contract_error" for p in contract_prices.values()):
            warning_parts.append("Some ERC-20 contract prices could not be fetched; affected tokens were left unpriced.")
        warning = " ".join(warning_parts) or None

        total_eur = 0.0
        total_usd = 0.0
        coin_totals_by_symbol: dict[str, dict[str, float]] = {}
        coin_qty_by_symbol: dict[str, float] = {}
        for h in visible_holdings:
            sym = h["asset"]
            p = price_map.get(str(h.get("price_key") or ""), {"price_eur": 0, "price_usd": 0})
            qty = float(h["qty"] or 0.0)
            value_eur = h["qty"] * float(p.get("price_eur", 0) or 0)
            value_usd = h["qty"] * float(p.get("price_usd", 0) or 0)
            total_eur += value_eur
            total_usd += value_usd
            curr = coin_totals_by_symbol.get(sym) or {"eur": 0.0, "usd": 0.0}
            curr["eur"] += value_eur
            curr["usd"] += value_usd
            coin_totals_by_symbol[sym] = curr
            coin_qty_by_symbol[sym] = float(coin_qty_by_symbol.get(sym) or 0.0) + qty

        nft_totals_by_key: dict[str, dict[str, object]] = {}
        nfts_total_eur = 0.0
        nfts_total_usd = 0.0
        for row in synced_nfts:
            visibility = str(row.get("visibility") or "visible").strip().lower()
            if visibility != "visible":
                continue
            chain = str(row.get("chain") or "").strip().lower()
            contract = str(row.get("contract") or "").strip().lower()
            token_id = str(row.get("token_id") or "").strip()
            if not (chain and contract and token_id):
                continue
            key = f"{chain}:{contract}:{token_id}"
            value_eur = float(row.get("valuation_eur") or 0.0)
            value_usd = float(row.get("valuation_usd") or 0.0)
            nfts_total_eur += value_eur
            nfts_total_usd += value_usd
            nft_totals_by_key[key] = {
                "name": row.get("name") or key,
                "chain": chain,
                "contract": contract,
                "token_id": token_id,
                "eur": value_eur,
                "usd": value_usd,
            }

        history_meta = {
            "sync_trigger": trigger_mode,
            "hidden_holdings_count": hidden_holdings_count,
            "totals": {
                "coins_eur": total_eur,
                "coins_usd": total_usd,
                "nfts_eur": nfts_total_eur,
                "nfts_usd": nfts_total_usd,
                "portfolio_eur": total_eur + nfts_total_eur,
                "portfolio_usd": total_usd + nfts_total_usd,
            },
            "coins": [
                {
                    "key": sym,
                    "name": sym,
                    "eur": vals["eur"],
                    "usd": vals["usd"],
                    "qty": float(coin_qty_by_symbol.get(sym) or 0.0),
                    "unit_eur": (
                        float(vals["eur"]) / float(coin_qty_by_symbol.get(sym) or 0.0)
                        if float(coin_qty_by_symbol.get(sym) or 0.0) > 0
                        else 0.0
                    ),
                    "unit_usd": (
                        float(vals["usd"]) / float(coin_qty_by_symbol.get(sym) or 0.0)
                        if float(coin_qty_by_symbol.get(sym) or 0.0) > 0
                        else 0.0
                    ),
                }
                for sym, vals in sorted(coin_totals_by_symbol.items(), key=lambda kv: kv[1]["eur"], reverse=True)
            ],
            "nfts": [
                {"key": key, "qty": 1.0, "unit_eur": float(vals["eur"]), "unit_usd": float(vals["usd"]), **vals}
                for key, vals in sorted(nft_totals_by_key.items(), key=lambda kv: float(kv[1]["eur"]), reverse=True)
            ],
        }

        _set_state(progress=92, message="Persisting snapshot and holdings...")
        with get_session() as s:
            s.query(Holding).delete()
            s.query(Price).delete()
            s.query(NFTHolding).delete()
            for h in holdings:
                s.add(
                    Holding(
                        account_id=int(h["account_id"]),
                        asset_symbol=str(h["asset"]),
                        asset_name=str(h["chain"]) if h.get("chain") else None,
                        quantity=float(h["qty"]),
                        asset_key=str(h.get("asset_key") or _symbol_price_key(str(h["asset"]))),
                        price_key=str(h.get("price_key") or _symbol_price_key(str(h["asset"]))),
                        asset_kind=h.get("asset_kind"),
                        contract_address=h.get("contract_address"),
                        visibility=str(h.get("visibility") or "visible"),
                        risk_reason=h.get("risk_reason"),
                    )
                )
            price_symbol_by_key = {
                str(h.get("price_key") or _symbol_price_key(str(h["asset"]))): str(h["asset"])
                for h in visible_holdings
            }
            for price_key, sym in price_symbol_by_key.items():
                p = price_map.get(price_key, {"price_eur": 0.0, "price_usd": 0.0})
                s.add(
                    Price(
                        asset_symbol=sym,
                        price_eur=float(p.get("price_eur", 0.0) or 0.0),
                        price_usd=float(p.get("price_usd", 0.0) or 0.0),
                        price_key=price_key,
                    )
                )
            for row in synced_nfts:
                s.add(
                    NFTHolding(
                        account_id=int(row.get("account_id") or 0),
                        chain=str(row.get("chain") or ""),
                        contract=str(row.get("contract") or ""),
                        token_id=str(row.get("token_id") or ""),
                        name=row.get("name"),
                        collection=row.get("collection"),
                        owner=row.get("owner"),
                        valuation_symbol=row.get("valuation_symbol"),
                        valuation_native=float(row.get("valuation_native") or 0),
                        valuation_source=row.get("valuation_source"),
                        valuation_confidence=row.get("valuation_confidence"),
                        valuation_usd=float(row.get("valuation_usd") or 0),
                        valuation_eur=float(row.get("valuation_eur") or 0),
                        is_spam=bool(row.get("is_spam", False)),
                        has_floor_or_last_sale=bool(row.get("has_floor_or_last_sale", False)),
                        visibility=str(row.get("visibility") or "visible"),
                    )
                )
            # Keep a single historical snapshot per UTC day (latest run wins).
            _persist_daily_snapshot(
                s,
                total_eur=total_eur,
                total_usd=total_usd,
                holdings_count=len(visible_holdings),
                symbols_count=len({str(h["asset"]) for h in visible_holdings}),
                nfts_count=len(synced_nfts),
                meta_payload=history_meta,
            )
            s.commit()

        finished = _utc_now_iso()
        _set_state(
            status="completed",
            progress=100,
            message=(
                f"Sync completed: {len(visible_holdings)} visible holdings, "
                f"{hidden_holdings_count} suspicious hidden, {len(synced_nfts)} NFTs, "
                f"total EUR {total_eur:.2f}, USD {total_usd:.2f}"
            ),
            finished_at=finished,
            last_error=None,
            warning=warning,
            holdings_count=len(visible_holdings),
            nfts_count=len(synced_nfts),
            total_eur=total_eur,
            total_usd=total_usd,
        )
    except Exception as exc:
        log.exception("sync failed")
        _set_state(
            status="failed",
            progress=100,
            message=f"Sync failed: {exc}",
            finished_at=_utc_now_iso(),
            last_error=str(exc),
            warning=_wallet_rpc_warning(),
            holdings_count=None,
            nfts_count=None,
            total_eur=None,
            total_usd=None,
        )
