import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models import DeviceLatest, Pond
from app.models.enums import PondStatus
from app.repositories.alert import TenantAlertRepository
from app.repositories.farm import FarmRepository, PondRepository
from app.repositories.settings import load_settings
from app.repositories.telemetry import TenantTelemetryRepository
from app.schemas.resources import (
    DashboardOut,
    DashboardSummary,
    DeviceReading,
    FarmOut,
    PondDetail,
    PondSummary,
)


def _device_reading(latest: DeviceLatest, cutoff: datetime) -> DeviceReading:
    return DeviceReading(
        device_id=latest.device_id,
        ts=latest.ts,
        is_stale=latest.ts < cutoff,
        dissolved_oxygen=latest.dissolved_oxygen,
        temperature=latest.temperature,
        ph=latest.ph,
        salinity=latest.salinity,
        ammonia=latest.ammonia,
        extra=latest.extra,
    )


def _pond_summary(pond: Pond, readings: Sequence[DeviceReading]) -> dict:
    """A stale value must not look like a current one, so it is left out."""
    oxygen = [
        r.dissolved_oxygen
        for r in readings
        if not r.is_stale and r.dissolved_oxygen is not None
    ]
    return {
        "id": pond.id,
        "farm_id": pond.farm_id,
        "name": pond.name,
        "status": pond.status,
        "dissolved_oxygen": min(oxygen, default=None),
        "last_reading_at": max((r.ts for r in readings), default=None),
    }


class DashboardService:
    def __init__(self, session: AsyncSession, org_id: uuid.UUID) -> None:
        self.session = session
        self.farms = FarmRepository(session, org_id)
        self.ponds = PondRepository(session, org_id)
        self.telemetry = TenantTelemetryRepository(session, org_id)
        self.alerts = TenantAlertRepository(session, org_id)

    async def _readings(
        self, pond_ids: Sequence[uuid.UUID], now: datetime
    ) -> dict[uuid.UUID, list[DeviceReading]]:
        minutes = (await load_settings(self.session))["offline_timeout_minutes"]
        cutoff = now - timedelta(minutes=minutes)
        by_pond: dict[uuid.UUID, list[DeviceReading]] = defaultdict(list)
        for latest, pond_id in await self.telemetry.latest_for_ponds(pond_ids, now):
            by_pond[pond_id].append(_device_reading(latest, cutoff))
        return by_pond

    async def farm_dashboard(self, farm_id: uuid.UUID, now: datetime) -> DashboardOut:
        farm = await self.farms.get(farm_id)
        if farm is None:
            raise not_found("Farm")

        ponds = await self.ponds.list_for(farm_id, limit=1000)
        pond_ids = [pond.id for pond in ponds]
        readings = await self._readings(pond_ids, now)
        summaries = [PondSummary(**_pond_summary(p, readings[p.id])) for p in ponds]
        oxygen = [s.dissolved_oxygen for s in summaries if s.dissolved_oxygen is not None]

        return DashboardOut(
            farm=FarmOut.model_validate(farm),
            summary=DashboardSummary(
                ponds_total=len(ponds),
                ponds_in_range=sum(s.status == PondStatus.OK for s in summaries),
                open_alerts=await self.alerts.count_live_for_ponds(pond_ids, now),
                median_dissolved_oxygen=median(oxygen) if oxygen else None,
            ),
            ponds=summaries,
        )

    async def pond_detail(self, pond_id: uuid.UUID, now: datetime) -> PondDetail:
        pond = await self.ponds.get(pond_id)
        if pond is None:
            raise not_found("Pond")
        devices = (await self._readings([pond.id], now))[pond.id]
        return PondDetail(**_pond_summary(pond, devices), devices=devices)
