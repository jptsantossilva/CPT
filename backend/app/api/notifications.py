from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import notifications

router = APIRouter(prefix="/admin/notifications", tags=["admin"])


class NotificationRecipientIn(BaseModel):
    type: str
    value: str
    enabled: bool = True


class NotificationCreate(BaseModel):
    name: str
    channel: str
    enabled: bool = True
    schedule_mode: str = "inherit"
    interval_value: int = 1
    interval_unit: str = "days"
    time_of_day: str = "00:00"
    day_of_week: str = "monday"
    timezone: str = "UTC"


class NotificationUpdate(BaseModel):
    name: str | None = None
    channel: str | None = None
    enabled: bool | None = None
    schedule_mode: str | None = None
    interval_value: int | None = None
    interval_unit: str | None = None
    time_of_day: str | None = None
    day_of_week: str | None = None
    timezone: str | None = None


class NotificationRecipientsUpdate(BaseModel):
    recipients: list[NotificationRecipientIn]


@router.get("/")
def list_notification_configs():
    return notifications.list_configs()


@router.post("/")
def create_notification_config(payload: NotificationCreate):
    try:
        return notifications.create_config(payload.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{notification_id}")
def get_notification_config(notification_id: int):
    try:
        return notifications.get_config(notification_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")


@router.put("/{notification_id}")
def update_notification_config(notification_id: int, payload: NotificationUpdate):
    data: dict[str, Any] = payload.dict(exclude_none=True)
    try:
        return notifications.update_config(notification_id, data)
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{notification_id}")
def delete_notification_config(notification_id: int):
    try:
        notifications.delete_config(notification_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"status": "deleted"}


@router.put("/{notification_id}/recipients")
def replace_notification_recipients(notification_id: int, payload: NotificationRecipientsUpdate):
    try:
        return notifications.replace_recipients(notification_id, [x.dict() for x in payload.recipients])
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{notification_id}/preview")
def preview_notification_message(notification_id: int):
    try:
        return notifications.preview(notification_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")


@router.post("/{notification_id}/run")
def run_notification_now(notification_id: int):
    try:
        return notifications.execute_notification(notification_id, reason="manual")
    except KeyError:
        raise HTTPException(status_code=404, detail="notification not found")
