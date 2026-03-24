from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import scheduler

router = APIRouter(prefix="/admin/sync-schedule", tags=["admin"])


class SyncScheduleUpdate(BaseModel):
    enabled: bool
    interval_value: int
    interval_unit: str
    time_of_day: str = "00:00"
    day_of_week: str = "monday"


@router.get("/")
def get_sync_schedule():
    return scheduler.get_schedule()


@router.put("/")
def update_sync_schedule(payload: SyncScheduleUpdate):
    try:
        return scheduler.update_schedule(payload.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
