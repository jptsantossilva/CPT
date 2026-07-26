from datetime import date, datetime, timezone
from types import SimpleNamespace

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
