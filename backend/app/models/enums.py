"""Allowed values. Stored as plain strings so adding one needs no migration."""
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"


class PondStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    OK = "OK"
    LOW = "LOW"
    CRITICAL_ALERT = "CRITICAL_ALERT"
    NO_DATA = "NO_DATA"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"


class Severity(StrEnum):
    LOW = "low"
    CRITICAL = "critical"


class AlertKind(StrEnum):
    THRESHOLD = "threshold"
    NO_DATA = "no_data"


class AlertState(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class RuleOperator(StrEnum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    CANCELED = "canceled"


class SubscriptionState(StrEnum):
    """What a subscription means right now, worked out from its dates."""

    PENDING = "pending"
    ACTIVE = "active"
    GRACE = "grace"
    EXPIRED = "expired"
    CANCELED = "canceled"
