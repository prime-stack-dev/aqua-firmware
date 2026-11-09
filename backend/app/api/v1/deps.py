"""Shared request dependencies: who is calling, and what they may access."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import forbidden, not_found, unauthorized
from app.core.security import InvalidTokenError, decode_access_token
from app.models import Device, User
from app.models.enums import Role
from app.repositories.base import TenantRepository
from app.repositories.device import DeviceRepository
from app.repositories.user import UserRepository

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


@dataclass(frozen=True)
class Identity:
    user: User
    org_id: uuid.UUID | None


@dataclass(frozen=True)
class Member:
    """A logged-in user acting inside their organization."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    role: Role


async def get_identity(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Identity:
    if credentials is None:
        raise unauthorized("Not authenticated")
    try:
        user_id, org_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise unauthorized("Invalid token") from exc
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise unauthorized("Invalid token")
    return Identity(user=user, org_id=org_id)


async def get_member(
    session: SessionDep, identity: Annotated[Identity, Depends(get_identity)]
) -> Member:
    """Membership is read on every request, so removing a user works at once."""
    if identity.org_id is None:
        raise forbidden("This token has no organization")
    membership = await UserRepository(session).membership(identity.user.id, identity.org_id)
    if membership is None:
        raise forbidden("Not a member of this organization")
    return Member(user_id=identity.user.id, org_id=identity.org_id, role=Role(membership.role))


MemberDep = Annotated[Member, Depends(get_member)]


def require_roles(*roles: Role) -> Callable:
    async def check(member: MemberDep) -> Member:
        if member.role not in roles:
            raise forbidden("Your role does not allow this")
        return member

    return check


def tenant_repo(repository: type[TenantRepository]):
    """Build a repository limited to the caller's organization."""

    def provide(session: SessionDep, member: MemberDep) -> TenantRepository:
        return repository(session, member.org_id)

    return Depends(provide)


def utc_now() -> datetime:
    return datetime.now(UTC)


async def get_readable_device(
    device_id: uuid.UUID,
    devices: Annotated[DeviceRepository, tenant_repo(DeviceRepository)],
) -> Device:
    """A device the caller owns and has a valid subscription for."""
    device = await devices.get(device_id)
    if device is None:
        raise not_found("Device")
    if not await devices.has_access(device_id, utc_now()):
        raise forbidden("Subscription for this device has expired")
    return device
