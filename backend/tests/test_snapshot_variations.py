from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.app.services.history import compute_variations


def _snap(ts: datetime, eur: float, usd: float):
    return SimpleNamespace(timestamp=ts, total_eur=eur, total_usd=usd)


def test_compute_variations_returns_expected_periods():
    now = datetime(2026, 2, 28, 12, 0, 0)
    rows = [
        _snap(now - timedelta(days=10), 100.0, 110.0),
        _snap(now - timedelta(days=2), 120.0, 132.0),
        _snap(now - timedelta(hours=2), 130.0, 143.0),
        _snap(now - timedelta(minutes=30), 140.0, 154.0),
    ]

    out = compute_variations(rows, now=now)
    assert out["latest"]["total_eur"] == 140.0
    assert out["latest"]["total_usd"] == 154.0

    # 24h baseline should be the row from 2 days ago.
    p24 = out["periods"]["24h"]
    assert p24 is not None
    assert p24["baseline_total_eur"] == 120.0
    assert round(float(p24["change_pct_eur"]), 2) == 16.67

    # MAX baseline should be oldest row.
    pmax = out["periods"]["max"]
    assert pmax is not None
    assert pmax["baseline_total_eur"] == 100.0
    assert round(float(pmax["change_pct_eur"]), 2) == 40.0


def test_compute_variations_handles_empty_rows():
    out = compute_variations([])
    assert out["latest"] is None
    assert out["periods"]["max"] is None
