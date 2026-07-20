import json

from sqlmodel import Session, SQLModel, create_engine

from backend.app import db, main
from backend.app.api import snapshots as snapshots_api
from backend.app.models import Snapshot
from backend.app.services.snapshot_quality import audit_snapshot


def _meta(eth_qty: float, total_eur: float, total_usd: float) -> str:
    return json.dumps(
        {
            "totals": {
                "coins_eur": total_eur,
                "coins_usd": total_usd,
                "nfts_eur": 0.0,
                "nfts_usd": 0.0,
                "portfolio_eur": total_eur,
                "portfolio_usd": total_usd,
            },
            "coins": [
                {
                    "key": "ETH",
                    "name": "ETH",
                    "qty": eth_qty,
                    "eur": total_eur,
                    "usd": total_usd,
                }
            ],
            "nfts": [],
        }
    )


def test_snapshot_audit_detects_spoofed_eth_without_changing_data():
    normal = Snapshot(total_eur=60_000.0, total_usd=68_000.0, meta=_meta(0.25, 60_000.0, 68_000.0))
    contaminated = Snapshot(total_eur=1e60, total_usd=1.1e60, meta=_meta(2.25e58, 1e60, 1.1e60))

    assert audit_snapshot(normal) is None
    anomaly = audit_snapshot(contaminated)
    assert anomaly is not None
    assert anomaly["suggested_reason"] == "erc20_native_symbol_spoof"
    assert anomaly["detected_reasons"] == ["total_exceeds_safety_limit", "implausible_eth_quantity"]
    assert contaminated.is_valid is True


def test_snapshot_admin_can_audit_quarantine_and_restore(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_admin.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(snapshots_api, "get_session", lambda: Session(engine))
    monkeypatch.setattr(db, "get_session", lambda: Session(engine))

    with Session(engine) as session:
        session.add(Snapshot(total_eur=60_000.0, total_usd=68_000.0, meta=_meta(0.25, 60_000.0, 68_000.0)))
        session.add(Snapshot(total_eur=1e60, total_usd=1.1e60, meta=_meta(2.25e58, 1e60, 1.1e60)))
        session.commit()

    audit = snapshots_api.audit_snapshots()
    assert audit["scanned"] == 2
    assert audit["candidate_count"] == 1
    candidate_id = audit["candidates"][0]["id"]

    updated = snapshots_api.update_snapshot_validity(
        candidate_id,
        snapshots_api.SnapshotValidityPayload(is_valid=False, reason="erc20_native_symbol_spoof"),
    )
    assert updated["is_valid"] is False
    assert updated["invalid_reason"] == "erc20_native_symbol_spoof"
    assert updated["invalidated_at"] is not None
    assert len(snapshots_api.list_snapshots(status="invalid")) == 1

    history = main.portfolio_history()
    assert len(history["points"]) == 1
    assert history["points"][0]["totals"]["portfolio_usd"] == 68_000.0
    assert db.get_latest_snapshot().total_usd == 68_000.0

    restored = snapshots_api.update_snapshot_validity(
        candidate_id,
        snapshots_api.SnapshotValidityPayload(is_valid=True),
    )
    assert restored["is_valid"] is True
    assert restored["invalid_reason"] is None
    assert restored["invalidated_at"] is None
    assert len(main.portfolio_history()["points"]) == 2

