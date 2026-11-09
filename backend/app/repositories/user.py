import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update

from app.models import Membership, Organization, RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def membership(self, user_id: uuid.UUID, org_id: uuid.UUID) -> Membership | None:
        return await self.session.get(Membership, (user_id, org_id))

    async def memberships(self, user_id: uuid.UUID) -> Sequence[tuple[Membership, Organization]]:
        stmt = (
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.name)
        )
        return (await self.session.execute(stmt)).tuples().all()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Locks the row so one token cannot be exchanged twice at once."""
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def revoke_all(self, user_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
