import json
import logging
import smtplib
import threading
from html import escape
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import httpx
from sqlmodel import select

from .. import db
from ..config import settings
from ..models import (
    NotificationAnchor,
    NotificationAssetSnapshot,
    NotificationConfig,
    NotificationRecipient,
    NotificationRun,
    NotificationSnapshot,
    Snapshot,
)
from . import scheduler

log = logging.getLogger(__name__)

_ALLOWED_CHANNELS = {"email", "telegram"}
_ALLOWED_SCHEDULE_MODE = {"inherit", "custom"}
_ALLOWED_UNITS = {"minutes", "hours", "days", "weeks"}
_ALLOWED_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_CURRENCY_SETTING_KEY = "ui_currency_mode"
_ALLOWED_CURRENCIES = {"EUR", "USD"}
_MIN_MOVER_VALUE_USD = 10.0

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _as_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True)


def _format_sync_timestamp(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return "n/a"
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_sync_timestamp_short(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return "n/a"
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%d %b %H:%M UTC")


def _format_sync_gap(current: datetime | None, previous: datetime | None) -> str:
    if not isinstance(current, datetime) or not isinstance(previous, datetime):
        return "n/a"
    curr = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
    prev = previous if previous.tzinfo else previous.replace(tzinfo=timezone.utc)
    delta_seconds = int(abs((curr - prev).total_seconds()))
    days = delta_seconds // 86400
    hours = (delta_seconds % 86400) // 3600
    return f"{days}d {hours}h"


def _normalize_schedule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schedule_mode = str(payload.get("schedule_mode") or "inherit").strip().lower()
    if schedule_mode not in _ALLOWED_SCHEDULE_MODE:
        raise ValueError("schedule_mode must be one of: inherit, custom")

    interval_value = int(payload.get("interval_value") or 1)
    if interval_value < 1:
        raise ValueError("interval_value must be >= 1")

    interval_unit = str(payload.get("interval_unit") or "days").strip().lower()
    if interval_unit not in _ALLOWED_UNITS:
        raise ValueError("interval_unit must be one of: minutes, hours, days, weeks")

    time_of_day = str(payload.get("time_of_day") or "00:00").strip()
    if len(time_of_day) != 5 or time_of_day[2] != ":":
        raise ValueError("time_of_day must be in HH:MM format")
    hh, mm = time_of_day.split(":", 1)
    try:
        h = int(hh)
        m = int(mm)
    except Exception as exc:
        raise ValueError("time_of_day must be in HH:MM format") from exc
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("time_of_day must be in HH:MM format")

    day_of_week = str(payload.get("day_of_week") or "monday").strip().lower()
    if day_of_week not in _ALLOWED_DAYS:
        raise ValueError("day_of_week must be one of: monday, tuesday, wednesday, thursday, friday, saturday, sunday")

    timezone_name = str(payload.get("timezone") or "UTC").strip() or "UTC"

    return {
        "schedule_mode": schedule_mode,
        "interval_value": interval_value,
        "interval_unit": interval_unit,
        "time_of_day": time_of_day,
        "day_of_week": day_of_week,
        "timezone": timezone_name,
    }


def _normalize_channel(value: str) -> str:
    channel = str(value or "").strip().lower()
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError("channel must be one of: email, telegram")
    return channel


def _resolve_schedule(config: NotificationConfig) -> dict[str, Any]:
    if config.schedule_mode == "inherit":
        inherited = scheduler.get_schedule()
        return {
            "enabled": bool(inherited.get("enabled", False)),
            "interval_value": int(inherited.get("interval_value") or 1),
            "interval_unit": str(inherited.get("interval_unit") or "days"),
            "time_of_day": str(inherited.get("time_of_day") or "00:00"),
            "day_of_week": str(inherited.get("day_of_week") or "monday"),
        }
    return {
        "enabled": True,
        "interval_value": int(config.interval_value or 1),
        "interval_unit": str(config.interval_unit or "days"),
        "time_of_day": str(config.time_of_day or "00:00"),
        "day_of_week": str(config.day_of_week or "monday"),
    }


def get_notification_currency() -> str:
    raw = db.get_app_setting(_CURRENCY_SETTING_KEY)
    value = str(raw or "USD").strip().upper()
    return value if value in _ALLOWED_CURRENCIES else "USD"


def set_notification_currency(currency: str) -> str:
    value = str(currency or "").strip().upper()
    if value not in _ALLOWED_CURRENCIES:
        raise ValueError("currency must be one of: EUR, USD")
    db.set_app_setting(_CURRENCY_SETTING_KEY, value)
    return value


def _compute_next_run(after: datetime, schedule_cfg: dict[str, Any]) -> datetime:
    unit = str(schedule_cfg["interval_unit"]).strip().lower()
    interval_value = int(schedule_cfg["interval_value"])

    if unit == "minutes":
        return after + timedelta(minutes=interval_value)
    if unit == "hours":
        return after + timedelta(hours=interval_value)

    hh, mm = (int(x) for x in str(schedule_cfg.get("time_of_day") or "00:00").split(":", 1))
    candidate = after.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if unit == "days":
        if candidate <= after:
            candidate = candidate + timedelta(days=interval_value)
        return candidate

    target_dow = _ALLOWED_DAYS.index(str(schedule_cfg.get("day_of_week") or "monday").strip().lower())
    now_dow = after.weekday()
    days_ahead = (target_dow - now_dow) % 7
    candidate = after + timedelta(days=days_ahead)
    candidate = candidate.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= after:
        candidate = candidate + timedelta(weeks=interval_value)
    return candidate


def _collect_current_snapshot() -> tuple[float, float, dict[str, dict[str, Any]]]:
    assets = db.list_assets()
    nfts = db.list_nfts(include_hidden=False)

    total_eur = 0.0
    total_usd = 0.0
    items: dict[str, dict[str, Any]] = {}

    for row in assets:
        symbol = str(row.get("asset_symbol") or "").upper().strip()
        if not symbol:
            continue
        key = f"coin:{symbol}"
        value_eur = float(row.get("value_eur") or 0.0)
        value_usd = float(row.get("value_usd") or 0.0)
        total_eur += value_eur
        total_usd += value_usd
        cur = items.get(key)
        if not cur:
            items[key] = {
                "asset_type": "coin",
                "asset_key": key,
                "asset_label": symbol,
                "value_eur": value_eur,
                "value_usd": value_usd,
            }
        else:
            cur["value_eur"] = float(cur.get("value_eur") or 0.0) + value_eur
            cur["value_usd"] = float(cur.get("value_usd") or 0.0) + value_usd

    for row in nfts:
        chain = str(row.get("chain") or "").strip().lower()
        contract = str(row.get("contract") or "").strip().lower()
        token_id = str(row.get("token_id") or "").strip()
        if not chain or not contract or not token_id:
            continue
        key = f"nft:{chain}:{contract}:{token_id}"
        label = str(row.get("name") or "").strip() or f"{(row.get('collection') or 'NFT')} #{token_id}"
        value_eur = float(row.get("valuation_eur") or 0.0)
        value_usd = float(row.get("valuation_usd") or 0.0)
        total_eur += value_eur
        total_usd += value_usd
        items[key] = {
            "asset_type": "nft",
            "asset_key": key,
            "asset_label": label,
            "value_eur": value_eur,
            "value_usd": value_usd,
        }

    return total_eur, total_usd, items


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _snapshot_meta(snapshot: Snapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    raw = getattr(snapshot, "meta", None)
    if not raw:
        return {}
    try:
        out = json.loads(raw)
    except Exception:
        return {}
    return out if isinstance(out, dict) else {}


def _sync_snapshot_trigger(snapshot: Snapshot | None) -> str:
    meta = _snapshot_meta(snapshot)
    return str(meta.get("sync_trigger") or "manual").strip().lower()


def _extract_sync_snapshot_data(snapshot: Snapshot | None) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    if snapshot is None:
        return {
            "coins_eur": 0.0,
            "coins_usd": 0.0,
            "nfts_eur": 0.0,
            "nfts_usd": 0.0,
            "portfolio_eur": 0.0,
            "portfolio_usd": 0.0,
        }, {}

    meta = _snapshot_meta(snapshot)
    totals = meta.get("totals") if isinstance(meta.get("totals"), dict) else {}

    coins_eur = _safe_float(totals.get("coins_eur", getattr(snapshot, "total_eur", 0.0)))
    coins_usd = _safe_float(totals.get("coins_usd", getattr(snapshot, "total_usd", 0.0)))
    nfts_eur = _safe_float(totals.get("nfts_eur", 0.0))
    nfts_usd = _safe_float(totals.get("nfts_usd", 0.0))
    portfolio_eur = _safe_float(totals.get("portfolio_eur", coins_eur + nfts_eur))
    portfolio_usd = _safe_float(totals.get("portfolio_usd", coins_usd + nfts_usd))

    assets: dict[str, dict[str, Any]] = {}

    for row in meta.get("coins") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or row.get("name") or "").strip()
        if not key:
            continue
        label = str(row.get("name") or key).strip()
        qty = _safe_float(row.get("qty"))
        value_eur = _safe_float(row.get("eur"))
        value_usd = _safe_float(row.get("usd"))
        unit_eur = _safe_float(row.get("unit_eur", (value_eur / qty) if qty > 0 else 0.0))
        unit_usd = _safe_float(row.get("unit_usd", (value_usd / qty) if qty > 0 else 0.0))
        assets[f"coin:{key}"] = {
            "asset_type": "coin",
            "asset_key": f"coin:{key}",
            "asset_label": label,
            "qty": qty,
            "value_eur": value_eur,
            "value_usd": value_usd,
            "unit_eur": unit_eur,
            "unit_usd": unit_usd,
        }

    for row in meta.get("nfts") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        label = str(row.get("name") or key).strip()
        value_eur = _safe_float(row.get("eur"))
        value_usd = _safe_float(row.get("usd"))
        qty = _safe_float(row.get("qty", 1.0))
        assets[f"nft:{key}"] = {
            "asset_type": "nft",
            "asset_key": f"nft:{key}",
            "asset_label": label,
            "qty": qty if qty > 0 else 1.0,
            "value_eur": value_eur,
            "value_usd": value_usd,
            "unit_eur": _safe_float(row.get("unit_eur", value_eur)),
            "unit_usd": _safe_float(row.get("unit_usd", value_usd)),
        }

    totals_out = {
        "coins_eur": coins_eur,
        "coins_usd": coins_usd,
        "nfts_eur": nfts_eur,
        "nfts_usd": nfts_usd,
        "portfolio_eur": portfolio_eur,
        "portfolio_usd": portfolio_usd,
    }
    return totals_out, assets


def _load_latest_sync_pair() -> tuple[Snapshot | None, Snapshot | None]:
    with db.get_session() as s:
        rows = s.exec(select(Snapshot).order_by(Snapshot.timestamp.desc()).limit(2)).all()
    if not rows:
        return None, None
    current = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    return current, previous


def _load_base_snapshot(notification_id: int) -> tuple[NotificationSnapshot | None, dict[str, dict[str, Any]]]:
    with db.get_session() as s:
        anchor = s.get(NotificationAnchor, notification_id)
        if not anchor or not anchor.last_snapshot_id:
            return None, {}
        snap = s.get(NotificationSnapshot, int(anchor.last_snapshot_id))
        if not snap:
            return None, {}
        rows = s.exec(
            select(NotificationAssetSnapshot).where(NotificationAssetSnapshot.snapshot_id == snap.id)
        ).all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[str(row.asset_key)] = {
            "asset_type": row.asset_type,
            "asset_key": row.asset_key,
            "asset_label": row.asset_label,
            "value_eur": float(row.value_eur or 0.0),
            "value_usd": float(row.value_usd or 0.0),
        }
    return snap, out


def _compute_movers(
    current_assets: dict[str, dict[str, Any]],
    base_assets: dict[str, dict[str, Any]],
    currency: str = "EUR",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = "value_usd" if str(currency or "EUR").upper() == "USD" else "value_eur"
    moves: list[dict[str, Any]] = []
    for key, current in current_assets.items():
        base = base_assets.get(key)
        if not base:
            continue
        current_usd = float(current.get("value_usd") or 0.0)
        base_usd = float(base.get("value_usd") or 0.0)
        # Ignore illiquid/noisy assets and avoid fake spikes when an asset
        # crosses from <= 1 USD in the previous sync to >= 1 USD now.
        if current_usd <= _MIN_MOVER_VALUE_USD or base_usd <= _MIN_MOVER_VALUE_USD:
            continue
        old_value = float(base.get(selected) or 0.0)
        if old_value <= 0:
            continue
        new_value = float(current.get(selected) or 0.0)
        delta_abs = new_value - old_value
        delta_pct = (delta_abs / old_value) * 100.0
        moves.append(
            {
                "asset_key": key,
                "asset_label": str(current.get("asset_label") or key),
                "asset_type": str(current.get("asset_type") or "coin"),
                "currency": str(currency or "EUR").upper(),
                "delta_pct": delta_pct,
                "delta_abs": delta_abs,
                "current_value": new_value,
                "base_value": old_value,
            }
        )

    top_up = [m for m in moves if float(m["delta_pct"]) > 0]
    top_down = [m for m in moves if float(m["delta_pct"]) < 0]
    top_up.sort(key=lambda x: float(x["delta_pct"]), reverse=True)
    top_down.sort(key=lambda x: float(x["delta_pct"]))
    return top_up[:5], top_down[:5]


def _compute_unit_price_movers(
    current_assets: dict[str, dict[str, Any]],
    base_assets: dict[str, dict[str, Any]],
    currency: str = "EUR",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_unit = "unit_usd" if str(currency or "EUR").upper() == "USD" else "unit_eur"
    moves: list[dict[str, Any]] = []
    for key, current in current_assets.items():
        base = base_assets.get(key)
        if not base:
            continue
        current_usd = float(current.get("value_usd") or 0.0)
        base_usd = float(base.get("value_usd") or 0.0)
        if current_usd <= _MIN_MOVER_VALUE_USD or base_usd <= _MIN_MOVER_VALUE_USD:
            continue
        old_unit = float(base.get(selected_unit) or 0.0)
        if old_unit <= 0:
            continue
        new_unit = float(current.get(selected_unit) or 0.0)
        delta_abs = new_unit - old_unit
        delta_pct = (delta_abs / old_unit) * 100.0
        moves.append(
            {
                "asset_key": key,
                "asset_label": str(current.get("asset_label") or key),
                "asset_type": str(current.get("asset_type") or "coin"),
                "currency": str(currency or "EUR").upper(),
                "delta_pct": delta_pct,
                "delta_abs": delta_abs,
                "current_value": new_unit,
                "base_value": old_unit,
            }
        )

    top_up = [m for m in moves if float(m["delta_pct"]) > 0]
    top_down = [m for m in moves if float(m["delta_pct"]) < 0]
    top_up.sort(key=lambda x: float(x["delta_pct"]), reverse=True)
    top_down.sort(key=lambda x: float(x["delta_pct"]))
    return top_up[:5], top_down[:5]


def _render_message(
    *,
    currency: str,
    current_total: float,
    base_total: float | None,
    current_sync_ts: datetime | None,
    previous_sync_ts: datetime | None,
    top_up: list[dict[str, Any]],
    top_down: list[dict[str, Any]],
) -> tuple[str, str, str]:
    curr = "USD" if str(currency or "").upper() == "USD" else "EUR"
    curr_symbol = "$" if curr == "USD" else "€"
    current_sync = _format_sync_timestamp(current_sync_ts)
    previous_sync = _format_sync_timestamp(previous_sync_ts)
    current_sync_short = _format_sync_timestamp_short(current_sync_ts)
    previous_sync_short = _format_sync_timestamp_short(previous_sync_ts)
    sync_gap = _format_sync_gap(current_sync_ts, previous_sync_ts)
    delta_abs: float | None = None
    delta_pct: float | None = None
    if base_total is not None:
        base = float(base_total or 0.0)
        delta_abs = current_total - base
        if base > 0:
            delta_pct = (delta_abs / base) * 100.0

    lines = [
        "Portfolio Update",
        f"{curr_symbol}{current_total:,.2f}",
        (
            f"{'+' if delta_abs >= 0 else '-'}{curr_symbol}{abs(delta_abs):,.2f} "
            f"{'▲' if delta_abs >= 0 else '▼'} {delta_pct:+.2f}%"
            if delta_abs is not None and delta_pct is not None
            else (
                f"{'+' if delta_abs >= 0 else '-'}{curr_symbol}{abs(delta_abs):,.2f} (n/a)"
                if delta_abs is not None
                else "n/a (need at least 2 sync snapshots)"
            )
        ),
        f"{previous_sync_short} -> {current_sync_short} · {sync_gap}",
        "",
        "Top 5 up",
    ]
    if not top_up:
        lines.append("- none")
    for idx, item in enumerate(top_up, start=1):
        lines.append(f"{idx}. {item['asset_label']} ▲ {float(item['delta_pct']):+.2f}%")

    lines.append("")
    lines.append("Top 5 down")
    if not top_down:
        lines.append("- none")
    for idx, item in enumerate(top_down, start=1):
        lines.append(f"{idx}. {item['asset_label']} ▼ {float(item['delta_pct']):+.2f}%")

    body = "\n".join(lines)

    def _color_for(value: float) -> str:
        return "#16a34a" if value >= 0 else "#dc2626"

    def _fmt_colored_pct(value: float) -> str:
        return f"<span style=\"color:{_color_for(value)};font-weight:600;font-size:15px;line-height:1.1;\">{value:+.2f}%</span>"

    def _fmt_colored_amount(value: float) -> str:
        abs_value = abs(value)
        sign = "+" if value >= 0 else "-"
        return (
            f"<span style=\"color:{_color_for(value)};font-weight:600;font-size:15px;line-height:1.1;\">"
            f"{sign}{curr_symbol}{abs_value:,.2f}</span>"
        )

    if delta_abs is None:
        variation_html = "Change: n/a (need at least 2 sync snapshots)"
    elif delta_pct is None:
        variation_html = f"Change: {_fmt_colored_amount(delta_abs)} <span style=\"opacity:.72;\">(n/a)</span>"
    else:
        variation_html = (
            "Change: "
            f"{_fmt_colored_amount(delta_abs)} {_fmt_colored_pct(delta_pct)}"
        )

    top_up_html = "".join(
        f"<li>{escape(str(item.get('asset_label') or 'n/a'))} "
        f"<span style=\"color:#15803d;font-weight:700;font-size:13px;line-height:1.2;\">▲</span> "
        f"{_fmt_colored_pct(float(item.get('delta_pct') or 0.0))}</li>"
        for item in top_up
    ) or "<li>none</li>"
    top_down_html = "".join(
        f"<li>{escape(str(item.get('asset_label') or 'n/a'))} "
        f"<span style=\"color:#b91c1c;font-weight:700;font-size:13px;line-height:1.2;\">▼</span> "
        f"{_fmt_colored_pct(float(item.get('delta_pct') or 0.0))}</li>"
        for item in top_down
    ) or "<li>none</li>"

    change_amount_html = (
        _fmt_colored_amount(delta_abs) if delta_abs is not None else "<span style=\"opacity:.72;\">n/a</span>"
    )
    change_pct_html = (
        _fmt_colored_pct(delta_pct) if delta_pct is not None else "<span style=\"opacity:.72;\">n/a</span>"
    )
    trend_arrow = "▲" if (delta_abs is not None and delta_abs >= 0) else ("▼" if delta_abs is not None else "•")
    trend_color = "#15803d" if (delta_abs is not None and delta_abs >= 0) else ("#b91c1c" if delta_abs is not None else "#666")

    body_html = (
        "<div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#111;\">"
        "<div style=\"font-size:24px;font-weight:700;line-height:1.2;margin:0 0 12px 0;\">Portfolio Update</div>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" style=\"border-collapse:collapse;width:auto;margin:0 0 4px 0;\">"
        "<tr>"
        "<td style=\"line-height:1.1;white-space:nowrap;vertical-align:bottom;\">"
        f"<span style=\"font-size:22px;font-weight:700;\">{curr_symbol}{current_total:,.2f}</span>"
        "</td>"
        "<td style=\"vertical-align:bottom;white-space:nowrap;padding-left:10px;\">"
        "<span style=\"display:inline-flex;align-items:flex-end;gap:4px;\">"
        f"{change_amount_html}"
        "<span style=\"display:inline-block;width:8px;\"></span>"
        f"<span style=\"color:{trend_color};font-weight:700;font-size:13px;line-height:1.2;\">{trend_arrow}</span>"
        " "
        f"{change_pct_html}"
        "</span>"
        "</td>"
        "</tr>"
        "</table>"
        f"<p style=\"margin:0 0 14px 0;color:#666;font-size:12px;\">{escape(previous_sync_short)} -&gt; {escape(current_sync_short)} "
        f"&middot; {escape(sync_gap)}</p>"
        "<p style=\"margin:0 0 6px 0;font-size:15px;\"><strong>Top 5 up</strong></p>"
        f"<ol style=\"margin:0 0 12px 20px;padding:0;\">{top_up_html}</ol>"
        "<p style=\"margin:2px 0 6px 0;font-size:15px;\"><strong>Top 5 down</strong></p>"
        f"<ol style=\"margin:0 0 0 20px;padding:0;\">{top_down_html}</ol>"
        "</div>"
    )
    subject_day = (
        (current_sync_ts if isinstance(current_sync_ts, datetime) else _utc_now())
        .astimezone(timezone.utc)
        .strftime("%Y-%m-%d")
    )
    subject = f"Portfolio update - {subject_day}"
    return subject, body, body_html


def _send_email(to_addr: str, subject: str, body: str, body_html: str | None = None) -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST not configured")
    if not settings.SMTP_FROM:
        raise RuntimeError("SMTP_FROM not configured")

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    use_tls = bool(settings.SMTP_USE_TLS)
    host = str(settings.SMTP_HOST)
    port = int(settings.SMTP_PORT or (587 if use_tls else 25))

    if use_tls:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(str(settings.SMTP_USERNAME), str(settings.SMTP_PASSWORD or ""))
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if settings.SMTP_USERNAME:
            smtp.login(str(settings.SMTP_USERNAME), str(settings.SMTP_PASSWORD or ""))
        smtp.send_message(msg)


def _send_telegram(chat_id: str, body: str) -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": body,
        "disable_web_page_preview": True,
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if not bool(data.get("ok")):
        raise RuntimeError(f"telegram send failed: {data}")


def _dispatch(
    channel: str,
    recipients: list[dict[str, Any]],
    subject: str,
    body: str,
    body_html: str | None = None,
) -> tuple[int, int, list[str]]:
    sent = 0
    failed = 0
    errors: list[str] = []

    for row in recipients:
        if not bool(row.get("enabled")):
            continue
        rtype = str(row.get("type") or "").strip().lower()
        if channel == "email" and rtype != "email":
            continue
        if channel == "telegram" and rtype != "telegram_chat":
            continue
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        try:
            if channel == "email":
                _send_email(value, subject, body, body_html)
            elif channel == "telegram":
                _send_telegram(value, body)
            else:
                raise RuntimeError(f"unsupported channel: {channel}")
            sent += 1
        except Exception as exc:
            failed += 1
            errors.append(f"{value}: {exc}")
    return sent, failed, errors


def _store_snapshot(
    *,
    notification_id: int,
    total_eur: float,
    total_usd: float,
    assets: dict[str, dict[str, Any]],
    base_snapshot_id: int | None,
) -> int:
    now = _utc_now()
    with db.get_session() as s:
        snap = NotificationSnapshot(
            notification_id=notification_id,
            captured_at=now,
            total_eur=total_eur,
            total_usd=total_usd,
            base_snapshot_id=base_snapshot_id,
        )
        s.add(snap)
        s.commit()
        s.refresh(snap)

        for item in assets.values():
            s.add(
                NotificationAssetSnapshot(
                    snapshot_id=int(snap.id),
                    asset_type=str(item.get("asset_type") or "coin"),
                    asset_key=str(item.get("asset_key") or ""),
                    asset_label=str(item.get("asset_label") or ""),
                    value_eur=float(item.get("value_eur") or 0.0),
                    value_usd=float(item.get("value_usd") or 0.0),
                )
            )
        s.commit()
        return int(snap.id)


def _upsert_anchor(notification_id: int, snapshot_id: int, sync_snapshot_id: int | None = None) -> None:
    now = _utc_now()
    with db.get_session() as s:
        anchor = s.get(NotificationAnchor, notification_id)
        if not anchor:
            anchor = NotificationAnchor(
                notification_id=notification_id,
                last_snapshot_id=snapshot_id,
                last_sync_snapshot_id=sync_snapshot_id,
                last_sent_at=now,
            )
            s.add(anchor)
        else:
            anchor.last_snapshot_id = snapshot_id
            if sync_snapshot_id is not None:
                anchor.last_sync_snapshot_id = sync_snapshot_id
            anchor.last_sent_at = now
            s.add(anchor)
        s.commit()


def _should_run_now(config: NotificationConfig, now: datetime) -> tuple[bool, datetime | None]:
    if not config.enabled:
        return False, None

    schedule_cfg = _resolve_schedule(config)
    if not schedule_cfg.get("enabled", True):
        return False, None

    with db.get_session() as s:
        anchor = s.get(NotificationAnchor, int(config.id))

    if str(config.schedule_mode or "").strip().lower() == "inherit":
        current_sync_snapshot, _prev = _load_latest_sync_pair()
        current_sync_snapshot_id = (
            int(current_sync_snapshot.id)
            if current_sync_snapshot and current_sync_snapshot.id is not None
            else None
        )
        if current_sync_snapshot_id is None:
            return False, None
        if _sync_snapshot_trigger(current_sync_snapshot) != "auto":
            return False, None
        last_consumed = int(anchor.last_sync_snapshot_id) if anchor and anchor.last_sync_snapshot_id is not None else None
        return current_sync_snapshot_id != last_consumed, getattr(current_sync_snapshot, "timestamp", None)

    reference = anchor.last_sent_at if anchor and anchor.last_sent_at else config.created_at
    if not reference:
        reference = now
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    next_run = _compute_next_run(reference, schedule_cfg)
    return now >= next_run, next_run


def execute_notification(notification_id: int, reason: str = "scheduled") -> dict[str, Any]:
    now = _utc_now()
    channel = ""
    recipient_rows: list[dict[str, Any]] = []
    with db.get_session() as s:
        config = s.get(NotificationConfig, notification_id)
        if not config:
            raise KeyError("notification not found")
        channel = str(config.channel or "").strip().lower()

        recipients = s.exec(
            select(NotificationRecipient).where(NotificationRecipient.notification_id == notification_id)
        ).all()
        recipient_rows = [
            {
                "type": str(r.type or "").strip().lower(),
                "value": str(r.value or "").strip(),
                "enabled": bool(r.enabled),
            }
            for r in recipients
        ]
        run = NotificationRun(
            notification_id=notification_id,
            status="running",
            reason=reason,
            started_at=now,
            scheduled_for=now,
            sent_recipients=0,
            failed_recipients=0,
            payload_json=None,
            error=None,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        run_id = int(run.id)

    selected_currency = get_notification_currency()
    current_sync_snapshot, previous_sync_snapshot = _load_latest_sync_pair()
    current_totals, current_assets = _extract_sync_snapshot_data(current_sync_snapshot)
    previous_totals, previous_assets = _extract_sync_snapshot_data(previous_sync_snapshot)
    current_total = float(
        current_totals["portfolio_usd"] if selected_currency == "USD" else current_totals["portfolio_eur"]
    )
    base_total = (
        float(previous_totals["portfolio_usd"] if selected_currency == "USD" else previous_totals["portfolio_eur"])
        if previous_sync_snapshot
        else None
    )
    top_up, top_down = _compute_unit_price_movers(
        current_assets, previous_assets, currency=selected_currency
    )
    subject, body, body_html = _render_message(
        currency=selected_currency,
        current_total=current_total,
        base_total=base_total,
        current_sync_ts=getattr(current_sync_snapshot, "timestamp", None),
        previous_sync_ts=getattr(previous_sync_snapshot, "timestamp", None),
        top_up=top_up,
        top_down=top_down,
    )

    snapshot_id = _store_snapshot(
        notification_id=notification_id,
        total_eur=float(current_totals["portfolio_eur"]),
        total_usd=float(current_totals["portfolio_usd"]),
        assets=current_assets,
        base_snapshot_id=None,
    )

    sent, failed, errors = _dispatch(channel, recipient_rows, subject, body, body_html)

    payload = {
        "subject": subject,
        "body": body,
        "body_html": body_html,
        "totals": {
            "currency": selected_currency,
            "current_total": current_total,
            "base_total": base_total,
            "current_total_eur": float(current_totals["portfolio_eur"]),
            "current_total_usd": float(current_totals["portfolio_usd"]),
            "current_snapshot_id": snapshot_id,
        },
        "sync_snapshots": {
            "current_sync_snapshot_id": int(current_sync_snapshot.id) if current_sync_snapshot and current_sync_snapshot.id is not None else None,
            "previous_sync_snapshot_id": int(previous_sync_snapshot.id) if previous_sync_snapshot and previous_sync_snapshot.id is not None else None,
        },
        "top_up": top_up,
        "top_down": top_down,
    }

    status = "sent" if sent > 0 and failed == 0 else ("partial" if sent > 0 else "failed")
    error = "; ".join(errors) if errors else None

    with db.get_session() as s:
        run = s.get(NotificationRun, run_id)
        if run:
            run.status = status
            run.error = error
            run.finished_at = _utc_now()
            run.sent_recipients = sent
            run.failed_recipients = failed
            run.payload_json = _as_json(payload)
            s.add(run)
            s.commit()

    if sent > 0:
        _upsert_anchor(
            notification_id,
            snapshot_id,
            int(current_sync_snapshot.id) if current_sync_snapshot and current_sync_snapshot.id is not None else None,
        )

    return {
        "run_id": run_id,
        "status": status,
        "sent_recipients": sent,
        "failed_recipients": failed,
        "error": error,
        "snapshot_id": snapshot_id,
    }


def list_configs() -> list[dict[str, Any]]:
    with db.get_session() as s:
        rows = s.exec(select(NotificationConfig).order_by(NotificationConfig.id.asc())).all()
        anchors = {a.notification_id: a for a in s.exec(select(NotificationAnchor)).all()}
        recipients = s.exec(select(NotificationRecipient).order_by(NotificationRecipient.id.asc())).all()

    recipients_by_cfg: dict[int, list[dict[str, Any]]] = {}
    for r in recipients:
        recipients_by_cfg.setdefault(int(r.notification_id), []).append(
            {
                "id": int(r.id) if r.id is not None else None,
                "type": r.type,
                "value": r.value,
                "enabled": bool(r.enabled),
            }
        )

    out: list[dict[str, Any]] = []
    now = _utc_now()
    for row in rows:
        due, next_run = _should_run_now(row, now)
        anchor = anchors.get(int(row.id)) if row.id is not None else None
        out.append(
            {
                "id": int(row.id) if row.id is not None else None,
                "name": row.name,
                "channel": row.channel,
                "enabled": bool(row.enabled),
                "schedule_mode": row.schedule_mode,
                "interval_value": int(row.interval_value),
                "interval_unit": row.interval_unit,
                "time_of_day": row.time_of_day,
                "day_of_week": row.day_of_week,
                "timezone": row.timezone,
                "created_at": _serialize_dt(row.created_at),
                "updated_at": _serialize_dt(row.updated_at),
                "last_sent_at": _serialize_dt(anchor.last_sent_at) if anchor else None,
                "next_run_at": _serialize_dt(next_run),
                "is_due": bool(due),
                "recipients": recipients_by_cfg.get(int(row.id), []),
            }
        )
    return out


def get_config(notification_id: int) -> dict[str, Any]:
    for item in list_configs():
        if int(item.get("id") or 0) == int(notification_id):
            return item
    raise KeyError("notification not found")


def create_config(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    channel = _normalize_channel(str(payload.get("channel") or ""))
    schedule = _normalize_schedule_payload(payload)

    now = _utc_now()
    with db.get_session() as s:
        row = NotificationConfig(
            name=name,
            channel=channel,
            enabled=bool(payload.get("enabled", True)),
            schedule_mode=str(schedule["schedule_mode"]),
            interval_value=int(schedule["interval_value"]),
            interval_unit=str(schedule["interval_unit"]),
            time_of_day=str(schedule["time_of_day"]),
            day_of_week=str(schedule["day_of_week"]),
            timezone=str(schedule["timezone"]),
            created_at=now,
            updated_at=now,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
    return get_config(int(row.id))


def update_config(notification_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with db.get_session() as s:
        row = s.get(NotificationConfig, notification_id)
        if not row:
            raise KeyError("notification not found")

        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            row.name = name

        if "channel" in payload:
            row.channel = _normalize_channel(str(payload.get("channel") or ""))

        if "enabled" in payload:
            row.enabled = bool(payload.get("enabled"))

        schedule_input = {
            "schedule_mode": payload.get("schedule_mode", row.schedule_mode),
            "interval_value": payload.get("interval_value", row.interval_value),
            "interval_unit": payload.get("interval_unit", row.interval_unit),
            "time_of_day": payload.get("time_of_day", row.time_of_day),
            "day_of_week": payload.get("day_of_week", row.day_of_week),
            "timezone": payload.get("timezone", row.timezone),
        }
        schedule = _normalize_schedule_payload(schedule_input)
        row.schedule_mode = str(schedule["schedule_mode"])
        row.interval_value = int(schedule["interval_value"])
        row.interval_unit = str(schedule["interval_unit"])
        row.time_of_day = str(schedule["time_of_day"])
        row.day_of_week = str(schedule["day_of_week"])
        row.timezone = str(schedule["timezone"])
        row.updated_at = _utc_now()

        s.add(row)
        s.commit()

    return get_config(notification_id)


def delete_config(notification_id: int) -> None:
    with db.get_session() as s:
        row = s.get(NotificationConfig, notification_id)
        if not row:
            raise KeyError("notification not found")

        recipients = s.exec(
            select(NotificationRecipient).where(NotificationRecipient.notification_id == notification_id)
        ).all()
        runs = s.exec(select(NotificationRun).where(NotificationRun.notification_id == notification_id)).all()
        snaps = s.exec(
            select(NotificationSnapshot).where(NotificationSnapshot.notification_id == notification_id)
        ).all()

        snap_ids = [int(x.id) for x in snaps if x.id is not None]
        if snap_ids:
            assets = s.exec(
                select(NotificationAssetSnapshot).where(NotificationAssetSnapshot.snapshot_id.in_(snap_ids))
            ).all()
            for a in assets:
                s.delete(a)

        for rec in recipients:
            s.delete(rec)
        for run in runs:
            s.delete(run)
        for snap in snaps:
            s.delete(snap)

        anchor = s.get(NotificationAnchor, notification_id)
        if anchor:
            s.delete(anchor)

        s.delete(row)
        s.commit()


def replace_recipients(notification_id: int, recipients: list[dict[str, Any]]) -> dict[str, Any]:
    clean_rows: list[dict[str, Any]] = []
    for row in recipients:
        rtype = str(row.get("type") or "").strip().lower()
        value = str(row.get("value") or "").strip()
        if not rtype or not value:
            continue
        if rtype not in {"email", "telegram_chat"}:
            raise ValueError("recipient type must be one of: email, telegram_chat")
        clean_rows.append(
            {
                "type": rtype,
                "value": value,
                "enabled": bool(row.get("enabled", True)),
            }
        )

    with db.get_session() as s:
        cfg = s.get(NotificationConfig, notification_id)
        if not cfg:
            raise KeyError("notification not found")
        existing = s.exec(
            select(NotificationRecipient).where(NotificationRecipient.notification_id == notification_id)
        ).all()
        for row in existing:
            s.delete(row)
        for row in clean_rows:
            s.add(
                NotificationRecipient(
                    notification_id=notification_id,
                    type=row["type"],
                    value=row["value"],
                    enabled=row["enabled"],
                    created_at=_utc_now(),
                )
            )
        cfg.updated_at = _utc_now()
        s.add(cfg)
        s.commit()

    return get_config(notification_id)


def preview(notification_id: int) -> dict[str, Any]:
    with db.get_session() as s:
        cfg = s.get(NotificationConfig, notification_id)
        if not cfg:
            raise KeyError("notification not found")
    selected_currency = get_notification_currency()
    current_sync_snapshot, previous_sync_snapshot = _load_latest_sync_pair()
    current_totals, current_assets = _extract_sync_snapshot_data(current_sync_snapshot)
    previous_totals, previous_assets = _extract_sync_snapshot_data(previous_sync_snapshot)
    current_total = float(
        current_totals["portfolio_usd"] if selected_currency == "USD" else current_totals["portfolio_eur"]
    )
    base_total = (
        float(previous_totals["portfolio_usd"] if selected_currency == "USD" else previous_totals["portfolio_eur"])
        if previous_sync_snapshot
        else None
    )
    top_up, top_down = _compute_unit_price_movers(
        current_assets, previous_assets, currency=selected_currency
    )
    subject, body, body_html = _render_message(
        currency=selected_currency,
        current_total=current_total,
        base_total=base_total,
        current_sync_ts=getattr(current_sync_snapshot, "timestamp", None),
        previous_sync_ts=getattr(previous_sync_snapshot, "timestamp", None),
        top_up=top_up,
        top_down=top_down,
    )
    return {
        "notification_id": notification_id,
        "channel": cfg.channel,
        "subject": subject,
        "body": body,
        "body_html": body_html,
        "currency": selected_currency,
        "current_total": current_total,
        "base_total": base_total,
        "current_total_eur": float(current_totals["portfolio_eur"]),
        "current_total_usd": float(current_totals["portfolio_usd"]),
        "current_sync_snapshot_id": int(current_sync_snapshot.id) if current_sync_snapshot and current_sync_snapshot.id is not None else None,
        "previous_sync_snapshot_id": int(previous_sync_snapshot.id) if previous_sync_snapshot and previous_sync_snapshot.id is not None else None,
        "top_up": top_up,
        "top_down": top_down,
    }


def run_due_notifications() -> None:
    now = _utc_now()
    with db.get_session() as s:
        rows = s.exec(select(NotificationConfig).where(NotificationConfig.enabled == True)).all()  # noqa: E712

    for row in rows:
        try:
            due, _next = _should_run_now(row, now)
            if not due:
                continue
            execute_notification(int(row.id), reason="scheduled")
        except Exception:
            log.exception("failed to run scheduled notification id=%s", row.id)


def _loop() -> None:
    while not _stop_event.is_set():
        try:
            run_due_notifications()
            _stop_event.wait(10)
        except Exception:
            log.exception("notification scheduler loop failed; retrying")
            _stop_event.wait(5)


def start() -> None:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="notification-scheduler", daemon=True)
        _thread.start()


def stop() -> None:
    global _thread
    _stop_event.set()
    t = _thread
    if t and t.is_alive():
        t.join(timeout=2)
    _thread = None
