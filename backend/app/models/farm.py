import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin
from app.models.enums import PondStatus


class Farm(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "farms"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))


class Pond(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "ponds"
    __table_args__ = (UniqueConstraint("farm_id", "name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(32), default=PondStatus.UNKNOWN, server_default=PondStatus.UNKNOWN.value
    )
