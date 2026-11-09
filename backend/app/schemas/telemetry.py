import math
import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Strict, so true/false and text are not silently turned into numbers.
MetricValue = Annotated[float, Field(strict=True)]

_EXTRA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_EXTRA_METRICS = 32


class TelemetryPayload(BaseModel):
    """What a device publishes. Unknown numeric fields are kept as extra sensors."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    ts: AwareDatetime
    dissolved_oxygen: MetricValue | None = None
    temperature: MetricValue | None = None
    ph: MetricValue | None = None
    salinity: MetricValue | None = None
    ammonia: MetricValue | None = None

    def extra_metrics(self) -> dict[str, float]:
        extras: dict[str, float] = {}
        for key, value in (self.model_extra or {}).items():
            if len(extras) == _MAX_EXTRA_METRICS:
                break
            is_number = isinstance(value, int | float) and not isinstance(value, bool)
            if is_number and _EXTRA_KEY.match(key) and math.isfinite(value):
                extras[key] = float(value)
        return extras


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    dissolved_oxygen: float | None
    temperature: float | None
    ph: float | None
    salinity: float | None
    ammonia: float | None


class LatestReadingOut(ReadingOut):
    device_id: uuid.UUID
    extra: dict[str, float] | None
    received_at: datetime


class HistoryOut(BaseModel):
    device_id: uuid.UUID
    resolution: Literal["raw", "hour", "day"]
    points: list[ReadingOut]
