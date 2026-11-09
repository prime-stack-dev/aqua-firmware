import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Double, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

METRIC_COLUMNS = ("dissolved_oxygen", "temperature", "ph", "salinity", "ammonia")


class ReadingColumns:
    """Columns shared by the full history and the latest-reading table."""

    # Stamped on every row, so a device that changes owner or pond
    # cannot expose or misplace its earlier data.
    org_id: Mapped[uuid.UUID | None] = mapped_column()
    pond_id: Mapped[uuid.UUID | None] = mapped_column()
    dissolved_oxygen: Mapped[float | None] = mapped_column(Double)
    temperature: Mapped[float | None] = mapped_column(Double)
    ph: Mapped[float | None] = mapped_column(Double)
    salinity: Mapped[float | None] = mapped_column(Double)
    ammonia: Mapped[float | None] = mapped_column(Double)
    # Sensors without their own column.
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Telemetry(ReadingColumns, Base):
    """Full history, split into monthly partitions.

    No foreign keys here: they would slow every insert on the busiest table.
    """

    __tablename__ = "telemetry"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    device_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class DeviceLatest(ReadingColumns, Base):
    """One row per device, so dashboards never have to scan history."""

    __tablename__ = "device_latest"
    __table_args__ = (Index(None, "org_id"), Index(None, "pond_id"))

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
