import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, and_, func, select

from app.models import Device, Plan, Subscription
from app.models.enums import SubscriptionStatus
from app.repositories.base import TenantRepository


def accessible_device_ids(now: datetime, org_id: uuid.UUID | None = None) -> Select:
    """Devices whose current owner has a subscription in force or in grace."""
    grace = func.make_interval(0, 0, 0, Plan.grace_days)
    stmt = (
        select(Subscription.device_id)
        .join(Plan, Plan.id == Subscription.plan_id)
        .join(
            Device,
            and_(Device.id == Subscription.device_id, Device.org_id == Subscription.org_id),
        )
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.starts_at <= now,
            Subscription.ends_at + grace >= now,
        )
    )
    if org_id is not None:
        stmt = stmt.where(Subscription.org_id == org_id)
    return stmt


class SubscriptionRepository(TenantRepository[Subscription]):
    model = Subscription

    async def list_with_plan(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[tuple[Subscription, Plan]]:
        stmt = (
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.org_id == self.org_id)
            .order_by(Subscription.ends_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.execute(stmt)).tuples().all()
