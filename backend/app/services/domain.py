"""Plain data passed between the ingest steps."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models import METRIC_COLUMNS, AlertRule


@dataclass(frozen=True, slots=True)
class DeviceRef:
    id: uuid.UUID
    org_id: uuid.UUID
    pond_id: uuid.UUID | None
    farm_id: uuid.UUID | None


@dataclass(slots=True)
class Reading:
    device: DeviceRef
    ts: datetime
    received_at: datetime
    values: dict[str, float | None]
    extra: dict[str, float] | None = None

    def value(self, metric: str) -> float | None:
        if metric in self.values:
            return self.values[metric]
        return (self.extra or {}).get(metric)

    def as_row(self) -> dict[str, Any]:
        return {
            "device_id": self.device.id,
            "ts": self.ts,
            "org_id": self.device.org_id,
            "pond_id": self.device.pond_id,
            **{metric: self.values.get(metric) for metric in METRIC_COLUMNS},
            "extra": self.extra,
            "received_at": self.received_at,
        }


@dataclass(slots=True)
class ReferenceData:
    """Lookups the ingest worker keeps in memory and refreshes periodically."""

    devices: dict[str, DeviceRef] = field(default_factory=dict)
    # Platform defaults are stored under None.
    rules_by_org: dict[uuid.UUID | None, list[AlertRule]] = field(default_factory=dict)
    metric_limits: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    settings: dict[str, int] = field(default_factory=dict)
