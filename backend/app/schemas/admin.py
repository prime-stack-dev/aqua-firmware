import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlatformOverviewOut(BaseModel):
    organizations_count: int
    users_count: int
    devices_count: int
    active_subscriptions_count: int
    open_alerts_count: int


class AdminOrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    members_count: int
    farms_count: int
    ponds_count: int
    devices_count: int
    created_at: datetime


class AdminDeviceOut(BaseModel):
    id: uuid.UUID
    serial: str
    name: str | None
    is_active: bool
    org_id: uuid.UUID | None
    org_name: str | None
    pond_id: uuid.UUID | None
    pond_name: str | None
    last_reading_at: datetime | None
    has_access: bool
