"""Background work done by the jobs worker."""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Device, DeviceLatest
from app.models.enums import AlertKind, AlertState, Severity
from app.repositories.alert import AlertRepository
from app.repositories.settings import load_settings
from app.services.pond_status import PondStatusService


async def try_job_lock(session: AsyncSession, job_id: int) -> bool:
    """Lets only one jobs worker do this job, held until the transaction ends."""
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": job_id}
    )
    return result.scalar_one()


async def detect_offline_devices(session: AsyncSession, now: datetime, minutes: int) -> int:
    """Open a no-data alert for each silent device. Returns how many were opened."""
    cutoff = now - timedelta(minutes=minutes)
    live = and_(
        Alert.device_id == Device.id,
        Alert.kind == AlertKind.NO_DATA,
        Alert.state != AlertState.CLOSED,
    )
    silent = await session.execute(
        select(Device.id, Device.org_id, Device.pond_id)
        .join(DeviceLatest, DeviceLatest.device_id == Device.id)
        .where(
            Device.org_id.is_not(None),
            Device.is_active,
            DeviceLatest.ts < cutoff,
            ~select(Alert.id).where(live).exists(),
        )
    )
    rows = [
        {
            "id": uuid.uuid4(),
            "org_id": org_id,
            "pond_id": pond_id,
            "device_id": device_id,
            "kind": AlertKind.NO_DATA,
            "severity": Severity.CRITICAL,
            "state": AlertState.OPEN,
            "opened_at": now,
        }
        for device_id, org_id, pond_id in silent
    ]
    if rows:
        await AlertRepository(session).insert_no_data_alerts(rows)
    return len(rows)


async def run_health_check(session: AsyncSession, now: datetime) -> int:
    minutes = (await load_settings(session))["offline_timeout_minutes"]
    opened = await detect_offline_devices(session, now, minutes)
    # All ponds, so expired subscriptions and silent devices are picked up.
    await PondStatusService(session).recompute(now, minutes)
    return opened


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def ensure_partitions(session: AsyncSession, now: datetime, months_ahead: int = 3) -> None:
    """Create upcoming monthly telemetry partitions. Safe to repeat."""
    year, month = now.year, now.month
    for _ in range(months_ahead + 1):
        end_year, end_month = _next_month(year, month)
        await session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS telemetry_y{year}m{month:02d} "
                "PARTITION OF telemetry "
                f"FOR VALUES FROM ('{year}-{month:02d}-01+00') "
                f"TO ('{end_year}-{end_month:02d}-01+00')"
            )
        )
        year, month = end_year, end_month
