import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AlertKind,
    AlertState,
    PondStatus,
    RuleOperator,
    Severity,
    SubscriptionState,
)


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class PondOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    farm_id: uuid.UUID
    name: str
    status: PondStatus


class DeviceOut(BaseModel):
    id: uuid.UUID
    serial: str
    name: str | None
    pond_id: uuid.UUID | None
    last_reading_at: datetime | None
    has_access: bool


class DeviceReading(BaseModel):
    device_id: uuid.UUID
    ts: datetime
    is_stale: bool
    dissolved_oxygen: float | None
    temperature: float | None
    ph: float | None
    salinity: float | None
    ammonia: float | None
    extra: dict[str, float] | None


class PondSummary(PondOut):
    # Lowest fresh reading in the pond. Empty when no fresh reading exists.
    dissolved_oxygen: float | None
    last_reading_at: datetime | None


class PondDetail(PondSummary):
    devices: list[DeviceReading]


class DashboardSummary(BaseModel):
    ponds_total: int
    ponds_in_range: int
    open_alerts: int
    median_dissolved_oxygen: float | None


class DashboardOut(BaseModel):
    farm: FarmOut
    summary: DashboardSummary
    ponds: list[PondSummary]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pond_id: uuid.UUID | None
    device_id: uuid.UUID
    kind: AlertKind
    metric: str | None
    severity: Severity
    state: AlertState
    threshold: float | None
    last_value: float | None
    opened_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: uuid.UUID | None = None
    closed_at: datetime | None


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Empty on platform defaults, which are read-only for customers.
    org_id: uuid.UUID | None
    farm_id: uuid.UUID | None
    pond_id: uuid.UUID | None
    metric: str
    operator: RuleOperator
    threshold: float
    severity: Severity
    clear_after: int
    enabled: bool


class AlertRuleCreate(BaseModel):
    farm_id: uuid.UUID | None = None
    pond_id: uuid.UUID | None = None
    metric: str = Field(max_length=64)
    operator: RuleOperator
    threshold: float = Field(allow_inf_nan=False)
    severity: Severity
    clear_after: int = Field(default=3, ge=1, le=60)
    enabled: bool = True

    @model_validator(mode="after")
    def one_scope_only(self) -> "AlertRuleCreate":
        if self.farm_id and self.pond_id:
            raise ValueError("Set farm_id or pond_id, not both")
        return self


class AlertRuleUpdate(BaseModel):
    operator: RuleOperator | None = None
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    clear_after: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    plan_name: str
    state: SubscriptionState
    starts_at: datetime
    ends_at: datetime
    access_until: datetime
