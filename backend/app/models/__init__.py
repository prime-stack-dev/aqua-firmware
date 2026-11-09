"""Importing this package registers every table with SQLAlchemy."""
from app.models.alert import Alert, AlertRule, MetricDefinition
from app.models.base import Base
from app.models.billing import Plan, Subscription
from app.models.device import Device
from app.models.farm import Farm, Pond
from app.models.identity import Membership, Organization, RefreshToken, User
from app.models.system import SystemSetting
from app.models.telemetry import METRIC_COLUMNS, DeviceLatest, Telemetry

__all__ = [
    "METRIC_COLUMNS",
    "Alert",
    "AlertRule",
    "Base",
    "Device",
    "DeviceLatest",
    "Farm",
    "Membership",
    "MetricDefinition",
    "Organization",
    "Plan",
    "Pond",
    "RefreshToken",
    "Subscription",
    "SystemSetting",
    "Telemetry",
    "User",
]
