import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Unscoped access. Only for system processes such as workers."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _select(self) -> Select:
        return select(self.model)

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = self._select().where(self.model.id == entity_id)
        return await self.session.scalar(stmt)

    async def list(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = self._select().limit(limit).offset(offset)
        return (await self.session.scalars(stmt)).all()

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity


class TenantRepository(BaseRepository[ModelT]):
    """Every query is limited to one organization.

    This is the single place that separates customers from each other.
    API code must use this class, or a subclass, for customer data.
    """

    def __init__(self, session: AsyncSession, org_id: uuid.UUID) -> None:
        super().__init__(session)
        self.org_id = org_id

    def _select(self) -> Select:
        return select(self.model).where(self.model.org_id == self.org_id)
