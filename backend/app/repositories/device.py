import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, select

from app.models import Device, DeviceLatest
from app.repositories.base import TenantRepository
from app.repositories.subscription import accessible_device_ids


class DeviceRepository(TenantRepository[Device]):
    model = Device

    async def has_access(self, device_id: uuid.UUID, now: datetime) -> bool:
        stmt = accessible_device_ids(now, self.org_id).where(
            Device.id == device_id
        )
        return await self.session.scalar(stmt.limit(1)) is not None

    async def list_with_status(
        self, now: datetime, limit: int = 100, offset: int = 0
    ) -> Sequence[tuple[Device, datetime | None, bool]]:
        """Each device, when it last reported, and whether it is accessible."""
        accessible = accessible_device_ids(now, self.org_id)
        stmt = (
            select(
                Device,
                DeviceLatest.ts,
                Device.id.in_(accessible).label("has_access"),
            )
            .outerjoin(
                DeviceLatest,
                and_(
                    DeviceLatest.device_id == Device.id,
                    DeviceLatest.org_id == self.org_id,
                ),
            )
            .where(Device.org_id == self.org_id)
            .order_by(Device.serial)
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.execute(stmt)).tuples().all()
