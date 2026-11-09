from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import Identity, SessionDep, get_identity
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrganizationAccess,
    RefreshRequest,
    TokenPair,
)
from app.services.auth import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenPair)
async def login(body: LoginRequest, session: SessionDep) -> TokenPair:
    return await AuthService(session).login(body.email, body.password, body.organization_id)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenPair:
    return await AuthService(session).refresh(body.refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: SessionDep) -> None:
    await AuthService(session).logout(body.refresh_token)


@router.get("/me", response_model=MeResponse)
async def me(
    identity: Annotated[Identity, Depends(get_identity)], session: SessionDep
) -> MeResponse:
    user = identity.user
    memberships = await UserRepository(session).memberships(user.id)
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=user.is_platform_admin,
        current_organization_id=identity.org_id,
        organizations=[
            OrganizationAccess(
                organization_id=org.id, organization_name=org.name, role=membership.role
            )
            for membership, org in memberships
        ],
    )
