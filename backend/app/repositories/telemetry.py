import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert

from app.models import METRIC_COLUMNS, Device, DeviceLatest, Telemetry
from app.repositories.base import BaseRepository, TenantRepository
from app.repositories.subscription import accessible_device_ids

# Keeps each statement below PostgreSQL's limit on query parameters.
_INSERT_CHUNK = 1000


class TelemetryRepository(BaseRepository[Telemetry]):
    """Writes from the ingest worker. Not for customer-facing code."""

    model = Telemetry

    async def insert_readings(self, rows: Sequence[dict[str, Any]]) -> None:
        for start in range(0, len(rows), _INSERT_CHUNK):
            stmt = insert(Telemetry).values(rows[start : start + _INSERT_CHUNK])
            await self.session.execute(
                stmt.on_conflict_do_nothing(index_elements=["device_id", "ts"])
            )

    async def latest_timestamps(
        self, device_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        stmt = select(DeviceLatest.device_id, DeviceLatest.ts).where(
            DeviceLatest.device_id.in_(device_ids)
        )
        return dict((await self.session.execute(stmt)).tuples().all())

    async def upsert_latest(self, rows: Sequence[dict[str, Any]]) -> None:
        """Rows must have one entry per device. Older data never overwrites newer."""
        for start in range(0, len(rows), _INSERT_CHUNK):
            stmt = insert(DeviceLatest).values(rows[start : start + _INSERT_CHUNK])
            updates = {
                column.name: stmt.excluded[column.name]
                for column in DeviceLatest.__table__.columns
                if column.name != "device_id"
            }
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["device_id"],
                    set_=updates,
                    where=stmt.excluded.ts > DeviceLatest.ts,
                )
            )


class TenantTelemetryRepository(TenantRepository[Telemetry]):
    """Reads for the customer API."""

    model = Telemetry

    async def latest(self, device_id: uuid.UUID) -> DeviceLatest | None:
        stmt = select(DeviceLatest).where(
            DeviceLatest.device_id == device_id, DeviceLatest.org_id == self.org_id
        )
        return await self.session.scalar(stmt)

    async def latest_for_ponds(
        self, pond_ids: Sequence[uuid.UUID], now: datetime
    ) -> Sequence[tuple[DeviceLatest, uuid.UUID]]:
        """Latest reading and current pond for each accessible device."""
        stmt = (
            select(DeviceLatest, Device.pond_id)
            .join(Device, Device.id == DeviceLatest.device_id)
            .where(
                Device.pond_id.in_(pond_ids),
                Device.org_id == self.org_id,
                DeviceLatest.org_id == self.org_id,
                Device.id.in_(accessible_device_ids(now, self.org_id)),
            )
        )
        return (await self.session.execute(stmt)).tuples().all()

    async def raw_history(
        self, device_id: uuid.UUID, start: datetime, end: datetime, limit: int
    ) -> Sequence[Telemetry]:
        stmt = (
            self._select()
            .where(Telemetry.device_id == device_id, Telemetry.ts >= start, Telemetry.ts <= end)
            .order_by(Telemetry.ts)
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()

    async def bucketed_history(
        self,
        device_id: uuid.UUID,
        start: datetime,
        end: datetime,
        unit: Literal["hour", "day"],
        limit: int,
    ) -> Sequence[Any]:
        """Averages per hour or day, with day boundaries in UTC."""
        bucket = func.date_trunc(
            literal_column(f"'{unit}'"), Telemetry.ts, literal_column("'UTC'")
        ).label("ts")
        averages = [func.avg(getattr(Telemetry, m)).label(m) for m in METRIC_COLUMNS]
        stmt = (
            select(bucket, *averages)
            .where(
                Telemetry.org_id == self.org_id,
                Telemetry.device_id == device_id,
                Telemetry.ts >= start,
                Telemetry.ts <= end,
            )
            .group_by(bucket)
            .order_by(bucket)
            .limit(limit)
        )
        return (await self.session.execute(stmt)).all()
