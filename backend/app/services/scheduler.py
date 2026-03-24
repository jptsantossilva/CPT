import json
import logging
import threading
import re
from datetime import datetime, timedelta, timezone

from .. import db
from . import sync

log = logging.getLogger(__name__)

_SETTING_KEY = "sync_schedule"
_DEFAULT_SCHEDULE = {
    "enabled": False,
    "interval_value": 1,
    "interval_unit": "days",  # minutes|hours|days|weeks
    "time_of_day": "00:00",  # HH:MM (UTC)
    "day_of_week": "monday",  # used when interval_unit=weeks
}
_ALLOWED_UNITS = {"minutes", "hours", "days", "weeks"}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_event = threading.Event()
_next_run_at: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_schedule(payload: dict) -> dict:
    enabled = bool(payload.get("enabled", False))
    try:
        interval_value = int(payload.get("interval_value", 1))
    except Exception as exc:
        raise ValueError("interval_value must be an integer") from exc
    if interval_value < 1:
        raise ValueError("interval_value must be >= 1")
    interval_unit = str(payload.get("interval_unit", "days")).strip().lower()
    if interval_unit not in _ALLOWED_UNITS:
        raise ValueError("interval_unit must be one of: minutes, hours, days, weeks")
    time_of_day = str(payload.get("time_of_day", "00:00")).strip()
    if not _TIME_RE.match(time_of_day):
        raise ValueError("time_of_day must be in HH:MM format")
    day_of_week = str(payload.get("day_of_week", "monday")).strip().lower()
    if day_of_week not in _DAYS:
        raise ValueError("day_of_week must be one of: monday, tuesday, wednesday, thursday, friday, saturday, sunday")
    return {
        "enabled": enabled,
        "interval_value": interval_value,
        "interval_unit": interval_unit,
        "time_of_day": time_of_day,
        "day_of_week": day_of_week,
    }


def _load_schedule_from_db() -> dict:
    raw = db.get_app_setting(_SETTING_KEY)
    if not raw:
        return dict(_DEFAULT_SCHEDULE)
    try:
        data = json.loads(raw)
    except Exception:
        log.warning("invalid sync schedule config in DB; resetting to defaults")
        return dict(_DEFAULT_SCHEDULE)
    try:
        return _normalize_schedule(data)
    except Exception:
        log.warning("invalid sync schedule payload in DB; resetting to defaults")
        return dict(_DEFAULT_SCHEDULE)


def _save_schedule_to_db(schedule: dict) -> None:
    db.set_app_setting(_SETTING_KEY, json.dumps(schedule))


def _compute_next_run(now: datetime, schedule: dict) -> datetime:
    unit = str(schedule["interval_unit"]).strip().lower()
    interval_value = int(schedule["interval_value"])
    if unit == "minutes":
        return now + timedelta(minutes=interval_value)
    if unit == "hours":
        return now + timedelta(hours=interval_value)

    time_of_day = str(schedule.get("time_of_day") or "00:00").strip()

    hour, minute = (int(x) for x in time_of_day.split(":", 1))
    today_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < today_at and unit == "days":
        return today_at
    if unit == "days":
        return today_at + timedelta(days=interval_value)

    target_dow = _DAYS.index(str(schedule.get("day_of_week") or "monday").strip().lower())
    now_dow = now.weekday()
    days_ahead = (target_dow - now_dow) % 7
    candidate = now + timedelta(days=days_ahead)
    candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(weeks=interval_value)
    return candidate


def get_schedule() -> dict:
    schedule = _load_schedule_from_db()
    with _lock:
        next_run = _next_run_at
    return {
        **schedule,
        "next_run_at": _serialize_dt(next_run),
    }


def update_schedule(payload: dict) -> dict:
    schedule = _normalize_schedule(payload)
    _save_schedule_to_db(schedule)
    now = _utc_now()
    with _lock:
        global _next_run_at
        _next_run_at = _compute_next_run(now, schedule) if schedule["enabled"] else None
    return get_schedule()


def _loop() -> None:
    global _next_run_at
    while not _stop_event.is_set():
        try:
            schedule = _load_schedule_from_db()
            if not schedule["enabled"]:
                with _lock:
                    _next_run_at = None
                _stop_event.wait(5)
                continue

            now = _utc_now()
            with _lock:
                if _next_run_at is None:
                    _next_run_at = _compute_next_run(now, schedule)
                next_run = _next_run_at

            if not next_run:
                _stop_event.wait(2)
                continue

            if now >= next_run:
                if sync.is_sync_running():
                    # Sync already running; retry shortly.
                    with _lock:
                        _next_run_at = now + timedelta(seconds=30)
                    _stop_event.wait(2)
                    continue

                log.info(
                    "auto sync triggered (every %s %s)",
                    schedule["interval_value"],
                    schedule["interval_unit"],
                )
                sync.sync_all()
                with _lock:
                    _next_run_at = _compute_next_run(_utc_now(), schedule)
                _stop_event.wait(1)
                continue

            wait_seconds = max(1.0, min((next_run - now).total_seconds(), 5.0))
            _stop_event.wait(wait_seconds)
        except Exception:
            log.exception("scheduler loop failed; retrying")
            _stop_event.wait(5)


def start() -> None:
    global _thread, _next_run_at
    with _lock:
        if _thread and _thread.is_alive():
            return
        schedule = _load_schedule_from_db()
        _next_run_at = _compute_next_run(_utc_now(), schedule) if schedule["enabled"] else None
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="sync-scheduler", daemon=True)
        _thread.start()


def stop() -> None:
    global _thread
    _stop_event.set()
    t = _thread
    if t and t.is_alive():
        t.join(timeout=2)
    _thread = None
