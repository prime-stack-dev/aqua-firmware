import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin
from app.models.enums import SubscriptionStatus


class Plan(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    max_devices: Mapped[int | None] = mapped_column(Integer)
    grace_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    raw_retention_days: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    hourly_retention_days: Mapped[int] = mapped_column(
        Integer, default=730, server_default="730"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Subscription(UUIDMixin, CreatedAtMixin, Base):
    """One device's paid period. Expiry is worked out from the dates."""

    __tablename__ = "subscriptions"
    __table_args__ = (Index(None, "device_id", "ends_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(
        String(32),
        default=SubscriptionStatus.ACTIVE,
        server_default=SubscriptionStatus.ACTIVE.value,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
