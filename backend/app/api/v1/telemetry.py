from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime

from app.api.v1.deps import get_readable_device, tenant_repo, utc_now
from app.core.errors import AppError, not_found
from app.models import Device
from app.repositories.telemetry import TenantTelemetryRepository
from app.schemas.telemetry import HistoryOut, LatestReadingOut, ReadingOut

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

_MAX_POINTS = 5000

Readings = Annotated[TenantTelemetryRepository, tenant_repo(TenantTelemetryRepository)]
ReadableDevice = Annotated[Device, Depends(get_readable_device)]


def pick_resolution(start: datetime, end: datetime) -> Literal["raw", "hour", "day"]:
    span = end - start
    if span <= timedelta(hours=48):
        return "raw"
    if span <= timedelta(days=60):
        return "hour"
    return "day"


@router.get("/{device_id}/latest", response_model=LatestReadingOut)
async def latest(device: ReadableDevice, readings: Readings):
    reading = await readings.latest(device.id)
    if reading is None:
        raise not_found("Reading")
    return reading


@router.get("/{device_id}/history", response_model=HistoryOut)
async def history(
    device: ReadableDevice,
    readings: Readings,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    """Defaults to the last 24 hours. Long ranges return hourly or daily averages."""
    end = end or utc_now()
    start = start or end - timedelta(hours=24)
    if start >= end:
        raise AppError(422, "start must be before end")

    resolution = pick_resolution(start, end)
    if resolution == "raw":
        rows = await readings.raw_history(device.id, start, end, _MAX_POINTS)
    else:
        rows = await readings.bucketed_history(device.id, start, end, resolution, _MAX_POINTS)
    return HistoryOut(
        device_id=device.id,
        resolution=resolution,
        points=[ReadingOut.model_validate(row) for row in rows],
    )
