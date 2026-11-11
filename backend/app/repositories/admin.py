import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.models import (
    Alert,
    Device,
    DeviceLatest,
    Farm,
    Membership,
    Organization,
    Pond,
    Subscription,
    User,
)
from app.models.enums import SubscriptionStatus
from app.repositories.base import BaseRepository
from app.repositories.subscription import accessible_device_ids


class PlatformAdminRepository(BaseRepository[Organization]):
    model = Organization

    async def overview(self, now: datetime) -> dict[str, int]:
        orgs_count = (await self.session.scalar(select(func.count(Organization.id)))) or 0
        users_count = (await self.session.scalar(select(func.count(User.id)))) or 0
        devices_count = (await self.session.scalar(select(func.count(Device.id)))) or 0
        active_subs = (
            await self.session.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.starts_at <= now,
                    Subscription.ends_at >= now,
                )
            )
        ) or 0
        open_alerts = (
            await self.session.scalar(
                select(func.count(Alert.id)).where(Alert.state != "closed")
            )
        ) or 0

        return {
            "organizations_count": orgs_count,
            "users_count": users_count,
            "devices_count": devices_count,
            "active_subscriptions_count": active_subs,
            "open_alerts_count": open_alerts,
        }

    async def list_organizations(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[tuple[Organization, int, int, int, int]]:
        members_sub = (
            select(Membership.org_id, func.count(Membership.user_id).label("cnt"))
            .group_by(Membership.org_id)
            .subquery()
        )
        farms_sub = (
            select(Farm.org_id, func.count(Farm.id).label("cnt"))
            .group_by(Farm.org_id)
            .subquery()
        )
        ponds_sub = (
            select(Pond.org_id, func.count(Pond.id).label("cnt"))
            .group_by(Pond.org_id)
            .subquery()
        )
        devices_sub = (
            select(Device.org_id, func.count(Device.id).label("cnt"))
            .group_by(Device.org_id)
            .subquery()
        )

        stmt = (
            select(
                Organization,
                func.coalesce(members_sub.c.cnt, 0).label("members_count"),
                func.coalesce(farms_sub.c.cnt, 0).label("farms_count"),
                func.coalesce(ponds_sub.c.cnt, 0).label("ponds_count"),
                func.coalesce(devices_sub.c.cnt, 0).label("devices_count"),
            )
            .outerjoin(members_sub, members_sub.c.org_id == Organization.id)
            .outerjoin(farms_sub, farms_sub.c.org_id == Organization.id)
            .outerjoin(ponds_sub, ponds_sub.c.org_id == Organization.id)
            .outerjoin(devices_sub, devices_sub.c.org_id == Organization.id)
            .order_by(Organization.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.execute(stmt)).tuples().all()

    async def list_all_devices(
        self, now: datetime, limit: int = 100, offset: int = 0
    ) -> Sequence[tuple[Device, str | None, str | None, datetime | None, bool]]:
        accessible = accessible_device_ids(now)
        stmt = (
            select(
                Device,
                Organization.name.label("org_name"),
                Pond.name.label("pond_name"),
                DeviceLatest.ts.label("last_reading_at"),
                Device.id.in_(accessible).label("has_access"),
            )
            .outerjoin(Organization, Organization.id == Device.org_id)
            .outerjoin(Pond, Pond.id == Device.pond_id)
            .outerjoin(
                DeviceLatest,
                DeviceLatest.device_id == Device.id,
            )
            .order_by(Device.serial)
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.execute(stmt)).tuples().all()
