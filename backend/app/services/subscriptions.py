from datetime import datetime, timedelta

from app.models import Plan, Subscription
from app.models.enums import SubscriptionState, SubscriptionStatus


def access_until(subscription: Subscription, plan: Plan) -> datetime:
    return subscription.ends_at + timedelta(days=plan.grace_days)


def subscription_state(
    subscription: Subscription, plan: Plan, now: datetime
) -> SubscriptionState:
    if subscription.status == SubscriptionStatus.CANCELED:
        return SubscriptionState.CANCELED
    if now < subscription.starts_at:
        return SubscriptionState.PENDING
    if now <= subscription.ends_at:
        return SubscriptionState.ACTIVE
    if now <= access_until(subscription, plan):
        return SubscriptionState.GRACE
    return SubscriptionState.EXPIRED
