import secrets
import uuid

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import AnyMember, MemberDep, OwnerOnly, SessionDep, utc_now
from app.core.errors import AppError, not_found
from app.core.security import hash_password
from app.models import Membership, User
from app.models.enums import Role
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.members import MemberInviteRequest, MemberOut, MemberUpdateRoleRequest

router = APIRouter(prefix="/organizations/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
async def list_members(member: AnyMember, session: SessionDep) -> list[MemberOut]:
    """List all team members of the caller's organization."""
    rows = await UserRepository(session).org_members(member.org_id)
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=Role(membership.role),
            is_active=user.is_active,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def invite_member(
    body: MemberInviteRequest, member: MemberDep, session: SessionDep
) -> MemberOut:
    """Add a new team member to the organization (Owner only)."""
    user_repo = UserRepository(session)
    existing_user = await user_repo.by_email(body.email)

    if existing_user:
        target_user = existing_user
        existing_membership = await user_repo.membership(target_user.id, member.org_id)
        if existing_membership:
            raise AppError(status.HTTP_409_CONFLICT, "User is already a member of this organization")
    else:
        password = body.password or secrets.token_urlsafe(16)
        target_user = user_repo.add_user(
            User(
                email=body.email,
                full_name=body.full_name,
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        await session.flush()

    membership = user_repo.add_membership(
        Membership(
            user_id=target_user.id,
            org_id=member.org_id,
            role=body.role.value,
        )
    )
    await session.commit()

    return MemberOut(
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=Role(membership.role),
        is_active=target_user.is_active,
        created_at=membership.created_at,
    )


@router.put("/{user_id}", response_model=MemberOut, dependencies=[OwnerOnly])
async def update_member_role(
    user_id: uuid.UUID, body: MemberUpdateRoleRequest, member: MemberDep, session: SessionDep
) -> MemberOut:
    """Change a team member's role (Owner only)."""
    user_repo = UserRepository(session)
    membership = await user_repo.membership(user_id, member.org_id)
    if not membership:
        raise not_found("Member")

    target_user = await user_repo.get(user_id)
    if not target_user:
        raise not_found("User")

    # Guard: prevent removing the last owner of the organization
    if membership.role == Role.OWNER.value and body.role != Role.OWNER:
        owner_count = await user_repo.count_owners(member.org_id)
        if owner_count <= 1:
            raise AppError(status.HTTP_409_CONFLICT, "Cannot demote the only owner of the organization")

    membership.role = body.role.value
    await session.commit()

    return MemberOut(
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=Role(membership.role),
        is_active=target_user.is_active,
        created_at=membership.created_at,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def remove_member(
    user_id: uuid.UUID, member: MemberDep, session: SessionDep
) -> None:
    """Remove a team member from the organization (Owner only)."""
    if user_id == member.user_id:
        raise AppError(status.HTTP_409_CONFLICT, "An owner cannot remove themselves from their organization")

    user_repo = UserRepository(session)
    membership = await user_repo.membership(user_id, member.org_id)
    if not membership:
        raise not_found("Member")

    if membership.role == Role.OWNER.value:
        owner_count = await user_repo.count_owners(member.org_id)
        if owner_count <= 1:
            raise AppError(status.HTTP_409_CONFLICT, "Cannot remove the only owner of the organization")

    await user_repo.remove_membership(membership)
    await RefreshTokenRepository(session).revoke_all(user_id, utc_now())
    await session.commit()
