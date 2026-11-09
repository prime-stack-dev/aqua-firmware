import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin
from app.models.enums import AlertState


class MetricDefinition(Base):
    """The sensors we know about and their physically possible range."""

    __tablename__ = "metric_definitions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(20))
    min_valid: Mapped[float | None] = mapped_column(Double)
    max_valid: Mapped[float | None] = mapped_column(Double)


class AlertRule(UUIDMixin, CreatedAtMixin, Base):
    """A threshold. No org means a platform default.

    The most specific rule wins: pond, then farm, then organization, then
    default. Rules are chosen per metric and severity.
    """

    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "farm_id", "pond_id", "metric", "severity", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("num_nonnulls(farm_id, pond_id) <= 1", name="one_scope"),
    )

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"))
    pond_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ponds.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(ForeignKey("metric_definitions.key"))
    operator: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[float] = mapped_column(Double)
    severity: Mapped[str] = mapped_column(String(16))
    # Good readings needed before the alert closes. Stops on/off flapping.
    clear_after: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Alert(UUIDMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_org_id_state_opened_at", "org_id", "state", text("opened_at DESC")),
        # At most one live alert per device and metric, even with many workers.
        Index(
            "uq_alerts_live_threshold",
            "device_id",
            "metric",
            unique=True,
            postgresql_where=text("kind = 'threshold' AND state <> 'closed'"),
        ),
        Index(
            "uq_alerts_live_no_data",
            "device_id",
            unique=True,
            postgresql_where=text("kind = 'no_data' AND state <> 'closed'"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    pond_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ponds.id", ondelete="SET NULL"))
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(
        String(16), default=AlertState.OPEN, server_default=AlertState.OPEN.value
    )
    threshold: Mapped[float | None] = mapped_column(Double)
    last_value: Mapped[float | None] = mapped_column(Double)
    ok_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
