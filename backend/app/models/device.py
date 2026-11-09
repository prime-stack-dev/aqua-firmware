import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class Device(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "devices"

    # The identifier a device uses in its MQTT topic and broker login.
    serial: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    # Empty while the device is still in our stock.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    pond_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ponds.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
