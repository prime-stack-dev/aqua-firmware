import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, forbidden, unauthorized
from app.core.security import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenPair


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    async def login(
        self, email: str, password: str, organization_id: uuid.UUID | None
    ) -> TokenPair:
        user = await self.users.by_email(email.strip().lower())
        if not verify_password(password, user.password_hash if user else None):
            raise unauthorized()
        if not user.is_active:
            raise unauthorized()

        org_id = await self._choose_organization(user, organization_id)
        pair = self._issue(user.id, org_id)
        await self.session.commit()
        return pair

    async def refresh(self, token: str) -> TokenPair:
        now = datetime.now(UTC)
        stored = await self.tokens.by_hash_for_update(hash_refresh_token(token))
        if stored is None:
            raise unauthorized("Invalid refresh token")

        if stored.revoked_at is not None:
            # A used token came back, so it may be stolen. End every session.
            await self.tokens.revoke_all(stored.user_id, now)
            await self.session.commit()
            raise unauthorized("Invalid refresh token")
        if stored.expires_at <= now:
            raise unauthorized("Invalid refresh token")

        user = await self.users.get(stored.user_id)
        if user is None or not user.is_active:
            raise unauthorized("Invalid refresh token")
        if stored.org_id and not await self.users.membership(user.id, stored.org_id):
            raise unauthorized("Invalid refresh token")

        stored.revoked_at = now
        pair = self._issue(user.id, stored.org_id)
        await self.session.commit()
        return pair

    async def logout(self, token: str) -> None:
        stored = await self.tokens.by_hash_for_update(hash_refresh_token(token))
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def _choose_organization(
        self, user: User, requested: uuid.UUID | None
    ) -> uuid.UUID | None:
        memberships = await self.users.memberships(user.id)
        org_ids = [membership.org_id for membership, _ in memberships]
        if requested is not None:
            if requested not in org_ids:
                raise forbidden("Not a member of this organization")
            return requested
        if len(org_ids) == 1:
            return org_ids[0]
        if len(org_ids) > 1:
            raise AppError(409, "organization_id is required for this user")
        if user.is_platform_admin:
            return None
        raise forbidden("User has no organization")

    def _issue(self, user_id: uuid.UUID, org_id: uuid.UUID | None) -> TokenPair:
        refresh = new_refresh_token()
        lifetime = timedelta(days=get_settings().refresh_token_days)
        self.tokens.add(
            RefreshToken(
                user_id=user_id,
                org_id=org_id,
                token_hash=hash_refresh_token(refresh),
                expires_at=datetime.now(UTC) + lifetime,
            )
        )
        return TokenPair(
            access_token=create_access_token(user_id, org_id), refresh_token=refresh
        )
