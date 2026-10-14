from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from backend.app import db
from backend.app.models import NotificationAnchor, NotificationConfig, Snapshot
from backend.app.services import notifications


def test_compute_movers_top5_split_positive_negative():
    current = {
        "coin:BTC": {"asset_type": "coin", "asset_label": "BTC", "value_eur": 120.0, "value_usd": 130.0},
        "coin:ETH": {"asset_type": "coin", "asset_label": "ETH", "value_eur": 80.0, "value_usd": 86.0},
        "coin:SOL": {"asset_type": "coin", "asset_label": "SOL", "value_eur": 40.0, "value_usd": 43.0},
        "nft:eth:a:1": {"asset_type": "nft", "asset_label": "NFT A", "value_eur": 90.0, "value_usd": 97.0},
    }
    base = {
        "coin:BTC": {"asset_type": "coin", "asset_label": "BTC", "value_eur": 100.0, "value_usd": 108.0},
        "coin:ETH": {"asset_type": "coin", "asset_label": "ETH", "value_eur": 100.0, "value_usd": 108.0},
        "coin:SOL": {"asset_type": "coin", "asset_label": "SOL", "value_eur": 80.0, "value_usd": 86.0},
        "nft:eth:a:1": {"asset_type": "nft", "asset_label": "NFT A", "value_eur": 60.0, "value_usd": 65.0},
    }

    top_up, top_down = notifications._compute_movers(current, base)
    assert len(top_up) == 2
    assert len(top_down) == 2
    assert top_up[0]["asset_label"] == "NFT A"
    assert top_down[0]["asset_label"] == "SOL"


def test_render_message_first_run_contains_na():
    subject, body, body_html = notifications._render_message(
        currency="USD",
        current_total=1080.0,
        base_total=None,
        current_sync_ts=datetime(2026, 3, 25, 14, 30, tzinfo=timezone.utc),
        previous_sync_ts=None,
        top_up=[],
        top_down=[],
    )
    assert subject == "Portfolio update - 2026-03-25"
    assert "Portfolio Update" in body
    assert "$1,080.00" in body
    assert "n/a (need at least 2 sync snapshots)" in body
    assert "n/a -> 25 Mar 14:30 UTC · n/a" in body
    assert "1,080.00" in body_html
    assert "$1,080.00" in body_html


def test_render_message_includes_global_pnl_in_plain_and_html_email():
    _subject, body, body_html = notifications._render_message(
        currency="EUR",
        current_total=1250.0,
        base_total=1000.0,
        current_sync_ts=datetime(2026, 3, 25, 14, 30, tzinfo=timezone.utc),
        previous_sync_ts=datetime(2026, 3, 24, 14, 30, tzinfo=timezone.utc),
        top_up=[],
        top_down=[],
        global_pnl=-125.5,
        global_pnl_pct=-12.55,
        global_pnl_status="loss",
    )
    assert "Global PnL: -€125.50 ▼ -12.55%" in body
    assert "Global PnL:" in body_html
    assert "-€125.50" in body_html
    assert "-12.55%" in body_html


def test_render_message_includes_counterparty_performance_and_pending_note():
    allocations = [
        {
            "counterparty_type": "person",
            "counterparty_name": "Rita",
            "allocation_pct": "80.74",
            "net_invested": "71372.00",
            "current_portfolio": "59264.68",
            "pnl": "-12107.32",
            "pnl_pct": "-16.96",
            "status": "loss",
            "pending_count": 1,
        },
        {
            "counterparty_type": "person",
            "counterparty_name": "João",
            "allocation_pct": "19.26",
            "net_invested": "16602.00",
            "current_portfolio": "14138.14",
            "pnl": "-2463.86",
            "pnl_pct": "-14.84",
            "status": "loss",
            "pending_count": 0,
        },
    ]

    _subject, body, body_html = notifications._render_message(
        currency="USD",
        current_total=73402.82,
        base_total=74000.0,
        current_sync_ts=datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc),
        previous_sync_ts=datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc),
        top_up=[],
        top_down=[],
        global_pnl=-14571.18,
        global_pnl_pct=-16.56,
        global_pnl_status="loss",
        counterparty_allocations=allocations,
        pending_cashflow_count=1,
    )

    assert "Performance by Counterparty" in body
    assert "Rita: Net $71,372.00 · Share 80.74% · Current $59,264.68" in body
    assert "PnL -$12,107.32 (-16.96%) · 1 pending" in body
    assert "Pending cash flows excluded: 1" in body
    assert "Performance by Counterparty" in body_html
    assert "Rita" in body_html
    assert "$59,264.68" in body_html
    assert "-$12,107.32" in body_html


def test_render_message_explains_skipped_price_identity_comparison():
    _subject, body, body_html = notifications._render_message(
        currency="USD",
        current_total=80_000.0,
        base_total=None,
        current_sync_ts=datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc),
        previous_sync_ts=datetime(2026, 10, 6, 0, 1, tzinfo=timezone.utc),
        top_up=[],
        top_down=[],
        comparison_note="price identity changed; comparison skipped",
    )

    assert "n/a (price identity changed; comparison skipped)" in body
    assert "price identity changed; comparison skipped" in body_html


def test_global_pnl_for_notification_uses_the_notification_snapshot(monkeypatch):
    cashflow = SimpleNamespace(
        flow_type="deposit",
        occurred_on=date(2026, 3, 1),
        amount_eur="1000.00",
        amount_usd="1100.00",
        counterparty_type="bank",
        counterparty_name="Bank",
    )

    class _Result:
        def all(self):
            return [cashflow]

    class _DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec(self, _query):
            return _Result()

    snapshot = Snapshot(
        timestamp=datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc),
        total_eur=1200.0,
        total_usd=1320.0,
    )
    monkeypatch.setattr(notifications.db, "get_session", lambda: _DummySession())

    pnl, pnl_pct, status = notifications._global_pnl_for_snapshot(snapshot, "USD")
    assert pnl == 220.0
    assert pnl_pct == 20.0
    assert status == "gain"


def test_notification_currency_validation_and_legacy_fallback():
    assert notifications._normalize_config_currency("usd") == "USD"
    assert notifications._config_currency(SimpleNamespace(currency=None)) == "EUR"
    assert notifications._config_currency(SimpleNamespace(currency="invalid")) == "EUR"
    with pytest.raises(ValueError, match="currency must be one of"):
        notifications._normalize_config_currency("GBP")


def test_notification_currency_compatibility_migration_defaults_existing_rows(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE notificationconfig (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)"))
        conn.execute(text("INSERT INTO notificationconfig (id, name) VALUES (1, 'Legacy')"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_notification_config_columns()

    assert "currency" in {column["name"] for column in inspect(engine).get_columns("notificationconfig")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT currency FROM notificationconfig WHERE id = 1")).scalar_one() == "EUR"


def test_preview_uses_notification_currency_instead_of_global_ui_currency(monkeypatch):
    now = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    cfg = NotificationConfig(
        id=9,
        name="EUR report",
        channel="email",
        currency="EUR",
        created_at=now,
        updated_at=now,
    )

    class _DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, model, key):
            return cfg if model is NotificationConfig and key == 9 else None

    current = SimpleNamespace(id=21, timestamp=now)
    performance = {
        "eur": {"pnl": "20.00", "pnl_pct": "20.00", "status": "gain"},
        "usd": {"pnl": "999.00", "pnl_pct": "999.00", "status": "gain"},
        "allocations": [],
        "pending": {"count": 0},
    }
    totals = {
        "coins_eur": 100.0,
        "coins_usd": 999.0,
        "nfts_eur": 0.0,
        "nfts_usd": 0.0,
        "portfolio_eur": 100.0,
        "portfolio_usd": 999.0,
    }
    monkeypatch.setattr(notifications.db, "get_session", lambda: _DummySession())
    monkeypatch.setattr(notifications, "get_notification_currency", lambda: "USD")
    monkeypatch.setattr(notifications, "_load_latest_sync_pair", lambda: (current, None))
    monkeypatch.setattr(notifications, "_performance_for_snapshot", lambda _snapshot: performance)
    monkeypatch.setattr(notifications, "_extract_sync_snapshot_data", lambda _snapshot: (totals, {}))
    monkeypatch.setattr(notifications, "_price_comparison_issue", lambda *args: None)
    monkeypatch.setattr(notifications, "_compute_unit_price_movers", lambda *args, **kwargs: ([], []))

    result = notifications.preview(9)

    assert result["currency"] == "EUR"
    assert result["current_total"] == 100.0
    assert "€100.00" in result["body"]
    assert "$999.00" not in result["body"]


def test_compute_next_run_minutes_and_weekly():
    now = datetime(2026, 3, 25, 10, 0, 0, tzinfo=timezone.utc)

    m = notifications._compute_next_run(
        now,
        {
            "interval_value": 15,
            "interval_unit": "minutes",
            "time_of_day": "00:00",
            "day_of_week": "monday",
        },
    )
    assert m.minute == 15

    w = notifications._compute_next_run(
        now,
        {
            "interval_value": 1,
            "interval_unit": "weeks",
            "time_of_day": "08:00",
            "day_of_week": "monday",
        },
    )
    assert w.weekday() == 0
    assert w.hour == 8


def test_compute_movers_ignores_assets_at_or_below_one_usd_threshold():
    current = {
        "coin:QNT": {
            "asset_type": "coin",
            "asset_label": "QNT",
            "value_eur": 50.0,
            "value_usd": 55.0,
        },
        "coin:TINY": {
            "asset_type": "coin",
            "asset_label": "TINY",
            "value_eur": 20.0,
            "value_usd": 20.0,
        },
    }
    base = {
        "coin:QNT": {
            "asset_type": "coin",
            "asset_label": "QNT",
            "value_eur": 1.0,
            "value_usd": 0.6,
        },
        "coin:TINY": {
            "asset_type": "coin",
            "asset_label": "TINY",
            "value_eur": 0.5,
            "value_usd": 0.8,
        },
    }

    top_up, top_down = notifications._compute_movers(current, base, currency="USD")
    assert top_up == []
    assert top_down == []


def test_unit_price_movers_skip_corrupted_legacy_usdc_unit_price():
    current = {
        "coin:USDC": {
            "asset_type": "coin", "asset_label": "USDC",
            "value_usd": 100.0, "unit_usd": 0.9995, "priced_qty_usd": 100.0,
        }
    }
    legacy = {
        "coin:USDC": {
            "asset_type": "coin", "asset_label": "USDC",
            "value_usd": 100.0, "unit_usd": 0.29875,
        }
    }

    top_up, top_down = notifications._compute_unit_price_movers(current, legacy, "USD")

    assert top_up == []
    assert top_down == []


def test_unit_price_movers_compare_corrected_usdc_prices():
    current = {
        "coin:USDC": {
            "asset_type": "coin", "asset_label": "USDC",
            "value_usd": 100.0, "unit_usd": 0.9995, "priced_qty_usd": 100.0,
        }
    }
    base = {
        "coin:USDC": {
            "asset_type": "coin", "asset_label": "USDC",
            "value_usd": 100.0, "unit_usd": 1.0, "priced_qty_usd": 100.0,
        }
    }

    top_up, top_down = notifications._compute_unit_price_movers(current, base, "USD")

    assert top_up == []
    assert len(top_down) == 1
    assert top_down[0]["delta_pct"] == pytest.approx(-0.05)


def test_unit_price_movers_skip_changed_coin_identity():
    current = {
        "coin:CVX": {
            "asset_type": "coin",
            "asset_label": "CVX",
            "value_usd": 360.0,
            "unit_usd": 2.12,
            "price_identity": "coingecko:convex-finance",
        }
    }
    base = {
        "coin:CVX": {
            "asset_type": "coin",
            "asset_label": "CVX",
            "value_usd": 35_000.0,
            "unit_usd": 206.14,
            "price_identity": "coingecko:wrong-cvx",
        }
    }

    top_up, top_down = notifications._compute_unit_price_movers(current, base, "USD")

    assert top_up == []
    assert top_down == []


def test_price_comparison_rejects_legacy_boundary_and_identity_change():
    current_snapshot = Snapshot(
        total_eur=320.0,
        total_usd=360.0,
        meta='{"price_identity_version":1}',
    )
    legacy_snapshot = Snapshot(total_eur=31_000.0, total_usd=35_000.0, meta="{}")
    current_assets = {
        "coin:CVX": {
            "asset_type": "coin",
            "value_usd": 360.0,
            "price_identity": "coingecko:convex-finance",
        }
    }
    legacy_assets = {
        "coin:CVX": {"asset_type": "coin", "value_usd": 35_000.0}
    }

    assert notifications._price_comparison_issue(
        current_snapshot,
        legacy_snapshot,
        current_assets,
        legacy_assets,
    ) == "price identity changed; comparison skipped"

    previous_snapshot = Snapshot(
        total_eur=31_000.0,
        total_usd=35_000.0,
        meta='{"price_identity_version":1}',
    )
    changed_assets = {
        "coin:CVX": {
            "asset_type": "coin",
            "value_usd": 35_000.0,
            "price_identity": "coingecko:wrong-cvx",
        }
    }
    assert notifications._price_comparison_issue(
        current_snapshot,
        previous_snapshot,
        current_assets,
        changed_assets,
    ) == "price identity changed; comparison skipped"


def test_should_run_now_inherit_requires_new_sync_snapshot(monkeypatch):
    now = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
    cfg = NotificationConfig(
        id=7,
        name="N1",
        channel="email",
        enabled=True,
        schedule_mode="inherit",
        interval_value=1,
        interval_unit="days",
        time_of_day="00:00",
        day_of_week="monday",
        timezone="UTC",
        created_at=now,
        updated_at=now,
    )

    class _DummySession:
        def __init__(self, anchor: NotificationAnchor | None):
            self._anchor = anchor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, model, key):
            if model is NotificationAnchor:
                return self._anchor
            return None

    monkeypatch.setattr(notifications, "_resolve_schedule", lambda _cfg: {"enabled": True})
    monkeypatch.setattr(
        notifications,
        "_load_latest_sync_pair",
        lambda: (SimpleNamespace(id=42, timestamp=now, meta='{"sync_trigger":"auto"}'), None),
    )

    monkeypatch.setattr(
        notifications.db,
        "get_session",
        lambda: _DummySession(NotificationAnchor(notification_id=7, last_sync_snapshot_id=41)),
    )
    due, _next = notifications._should_run_now(cfg, now)
    assert due is True

    monkeypatch.setattr(
        notifications.db,
        "get_session",
        lambda: _DummySession(NotificationAnchor(notification_id=7, last_sync_snapshot_id=42)),
    )
    due2, _next2 = notifications._should_run_now(cfg, now)
    assert due2 is False


def test_should_run_now_inherit_ignores_manual_sync_snapshot(monkeypatch):
    now = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
    cfg = NotificationConfig(
        id=8,
        name="N2",
        channel="email",
        enabled=True,
        schedule_mode="inherit",
        interval_value=1,
        interval_unit="days",
        time_of_day="00:00",
        day_of_week="monday",
        timezone="UTC",
        created_at=now,
        updated_at=now,
    )

    class _DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, model, key):
            if model is NotificationAnchor:
                return NotificationAnchor(notification_id=8, last_sync_snapshot_id=41)
            return None

    monkeypatch.setattr(notifications, "_resolve_schedule", lambda _cfg: {"enabled": True})
    monkeypatch.setattr(
        notifications,
        "_load_latest_sync_pair",
        lambda: (SimpleNamespace(id=42, timestamp=now, meta='{"sync_trigger":"manual"}'), None),
    )
    monkeypatch.setattr(notifications.db, "get_session", lambda: _DummySession())

    due, _next = notifications._should_run_now(cfg, now)
    assert due is False
