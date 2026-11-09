import uuid
from collections.abc import Sequence

from app.models import Farm, Pond
from app.repositories.base import TenantRepository


class FarmRepository(TenantRepository[Farm]):
    model = Farm


class PondRepository(TenantRepository[Pond]):
    model = Pond

    async def list_for(
        self, farm_id: uuid.UUID | None, limit: int = 100, offset: int = 0
    ) -> Sequence[Pond]:
        stmt = self._select().order_by(Pond.name).limit(limit).offset(offset)
        if farm_id is not None:
            stmt = stmt.where(Pond.farm_id == farm_id)
        return (await self.session.scalars(stmt)).all()
