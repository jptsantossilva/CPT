from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..db import get_session
from ..models import Snapshot
from ..services.snapshot_quality import audit_snapshot

router = APIRouter(prefix="/admin/snapshots", tags=["admin"])


class SnapshotValidityPayload(BaseModel):
    is_valid: bool
    reason: str | None = None


def _serialize(row: Snapshot, anomaly: dict | None = None) -> dict:
    return {
        "id": int(row.id) if row.id is not None else None,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "total_eur": float(row.total_eur or 0.0),
        "total_usd": float(row.total_usd or 0.0),
        "is_valid": bool(row.is_valid),
        "invalid_reason": row.invalid_reason,
        "invalidated_at": row.invalidated_at.isoformat() if row.invalidated_at else None,
        "anomaly": anomaly,
    }


@router.get("/")
def list_snapshots(status: str = "all", limit: int = 500):
    normalized_status = str(status or "all").strip().lower()
    if normalized_status not in {"all", "valid", "invalid"}:
        raise HTTPException(status_code=400, detail="status must be one of: all, valid, invalid")
    n = max(1, min(int(limit or 500), 5000))
    statement = select(Snapshot)
    if normalized_status == "valid":
        statement = statement.where(Snapshot.is_valid == True)  # noqa: E712
    elif normalized_status == "invalid":
        statement = statement.where(Snapshot.is_valid == False)  # noqa: E712
    statement = statement.order_by(Snapshot.timestamp.desc()).limit(n)
    with get_session() as session:
        rows = session.exec(statement).all()
    return [_serialize(row) for row in rows]


@router.post("/audit")
def audit_snapshots():
    with get_session() as session:
        rows = session.exec(
            select(Snapshot)
            .where(Snapshot.is_valid == True)  # noqa: E712
            .order_by(Snapshot.timestamp.desc())
        ).all()
    candidates = []
    for row in rows:
        anomaly = audit_snapshot(row)
        if anomaly:
            candidates.append(_serialize(row, anomaly))
    return {"scanned": len(rows), "candidate_count": len(candidates), "candidates": candidates}


@router.put("/{snapshot_id}/validity")
def update_snapshot_validity(snapshot_id: int, payload: SnapshotValidityPayload):
    with get_session() as session:
        row = session.get(Snapshot, snapshot_id)
        if not row:
            raise HTTPException(status_code=404, detail="snapshot not found")
        if payload.is_valid:
            row.is_valid = True
            row.invalid_reason = None
            row.invalidated_at = None
        else:
            reason = str(payload.reason or "manual_review").strip()
            if not reason:
                reason = "manual_review"
            row.is_valid = False
            row.invalid_reason = reason[:500]
            row.invalidated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize(row)

