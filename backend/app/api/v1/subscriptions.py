from typing import Annotated

from fastapi import APIRouter

from app.api.v1.deps import Limit, Offset, tenant_repo, utc_now
from app.repositories.subscription import SubscriptionRepository
from app.schemas.resources import SubscriptionOut
from app.services.subscriptions import access_until, subscription_state

router = APIRouter(tags=["subscriptions"])

Subscriptions = Annotated[SubscriptionRepository, tenant_repo(SubscriptionRepository)]


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    subscriptions: Subscriptions, limit: Limit = 100, offset: Offset = 0
):
    now = utc_now()
    return [
        SubscriptionOut(
            id=subscription.id,
            device_id=subscription.device_id,
            plan_name=plan.name,
            state=subscription_state(subscription, plan, now),
            starts_at=subscription.starts_at,
            ends_at=subscription.ends_at,
            access_until=access_until(subscription, plan),
        )
        for subscription, plan in await subscriptions.list_with_plan(limit, offset)
    ]
