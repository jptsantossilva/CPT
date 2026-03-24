import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.models import Snapshot
from backend.app.services import scheduler, sync


def test_scheduler_update_validates_payload(monkeypatch):
    stored: dict[str, object] = {
        "enabled": False,
        "interval_value": 1,
        "interval_unit": "days",
        "time_of_day": "00:00",
        "day_of_week": "monday",
    }

    monkeypatch.setattr(scheduler, "_save_schedule_to_db", lambda payload: stored.update(payload))
    monkeypatch.setattr(scheduler, "_load_schedule_from_db", lambda: dict(stored))

    try:
        scheduler.update_schedule({"enabled": True, "interval_value": 0, "interval_unit": "days"})
        assert False, "expected ValueError for interval_value=0"
    except ValueError:
        pass

    try:
        scheduler.update_schedule({"enabled": True, "interval_value": 1, "interval_unit": "months"})
        assert False, "expected ValueError for invalid unit"
    except ValueError:
        pass

    try:
        scheduler.update_schedule(
            {"enabled": True, "interval_value": 1, "interval_unit": "days", "time_of_day": "24:70"}
        )
        assert False, "expected ValueError for invalid time_of_day"
    except ValueError:
        pass

    try:
        scheduler.update_schedule(
            {
                "enabled": True,
                "interval_value": 1,
                "interval_unit": "weeks",
                "time_of_day": "00:00",
                "day_of_week": "funday",
            }
        )
        assert False, "expected ValueError for invalid day_of_week"
    except ValueError:
        pass

    out = scheduler.update_schedule(
        {
            "enabled": True,
            "interval_value": 1,
            "interval_unit": "weeks",
            "time_of_day": "00:00",
            "day_of_week": "monday",
        }
    )
    assert out["enabled"] is True
    assert out["interval_value"] == 1
    assert out["interval_unit"] == "weeks"
    assert out["time_of_day"] == "00:00"
    assert out["day_of_week"] == "monday"
    assert out.get("next_run_at")


def test_persist_daily_snapshot_replaces_same_day_entry():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        sync._persist_daily_snapshot(
            s,
            total_eur=100.0,
            total_usd=110.0,
            holdings_count=2,
            symbols_count=2,
        )
        s.commit()

        sync._persist_daily_snapshot(
            s,
            total_eur=200.0,
            total_usd=220.0,
            holdings_count=3,
            symbols_count=3,
        )
        s.commit()

        rows = s.exec(select(Snapshot)).all()
        assert len(rows) == 1
        snap = rows[0]
        assert float(snap.total_eur) == 200.0
        assert float(snap.total_usd or 0) == 220.0
        meta = json.loads(snap.meta or "{}")
        assert int(meta.get("holdings_count", 0)) == 3


def test_compute_next_run_weekly_uses_day_of_week_and_time():
    now = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)  # Saturday
    schedule_cfg = {
        "enabled": True,
        "interval_value": 1,
        "interval_unit": "weeks",
        "time_of_day": "00:00",
        "day_of_week": "monday",
    }
    out = scheduler._compute_next_run(now, schedule_cfg)
    assert out.weekday() == 0  # Monday
    assert out.hour == 0 and out.minute == 0
    assert out > now


def test_compute_next_run_minutes_and_hours():
    now = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)

    every_15m = {
        "enabled": True,
        "interval_value": 15,
        "interval_unit": "minutes",
        "time_of_day": "00:00",
        "day_of_week": "monday",
    }
    out_m = scheduler._compute_next_run(now, every_15m)
    assert out_m == now + timedelta(minutes=15)

    every_2h = {
        "enabled": True,
        "interval_value": 2,
        "interval_unit": "hours",
        "time_of_day": "00:00",
        "day_of_week": "monday",
    }
    out_h = scheduler._compute_next_run(now, every_2h)
    assert out_h == now + timedelta(hours=2)
