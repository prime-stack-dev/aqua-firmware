"""Unit tests for Role-Based Access Control (RBAC) and Member Management."""
import uuid

import httpx
import pytest

from app.api.v1.deps import Member, Identity, require_platform_admin, require_roles
from app.core.errors import AppError
from app.main import app
from app.models import User
from app.models.enums import Role


def create_member(role: Role) -> Member:
    return Member(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role=role)


def create_identity(is_platform_admin: bool = False) -> Identity:
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Test User",
        password_hash="fake",
        is_platform_admin=is_platform_admin,
    )
    return Identity(user=user, org_id=uuid.uuid4())


async def test_owner_role_allowed_for_owner_only_action():
    owner = create_member(Role.OWNER)
    checker = require_roles(Role.OWNER)
    assert await checker(owner) == owner


async def test_manager_role_forbidden_for_owner_only_action():
    manager = create_member(Role.MANAGER)
    checker = require_roles(Role.OWNER)
    with pytest.raises(AppError) as exc_info:
        await checker(manager)
    assert exc_info.value.status_code == 403
    assert "Your role does not allow this" in str(exc_info.value.detail)


async def test_viewer_role_forbidden_for_operator_action():
    viewer = create_member(Role.VIEWER)
    checker = require_roles(Role.OWNER, Role.MANAGER)
    with pytest.raises(AppError) as exc_info:
        await checker(viewer)
    assert exc_info.value.status_code == 403


async def test_manager_role_allowed_for_operator_action():
    manager = create_member(Role.MANAGER)
    checker = require_roles(Role.OWNER, Role.MANAGER)
    assert await checker(manager) == manager


async def test_platform_admin_dependency_allows_admin():
    admin_identity = create_identity(is_platform_admin=True)
    result = await require_platform_admin(admin_identity)
    assert result == admin_identity


async def test_platform_admin_dependency_rejects_regular_user():
    user_identity = create_identity(is_platform_admin=False)
    with pytest.raises(AppError) as exc_info:
        await require_platform_admin(user_identity)
    assert exc_info.value.status_code == 403
    assert "Platform admin access required" in str(exc_info.value.detail)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/organizations/members",
        "/api/v1/admin/overview",
        "/api/v1/admin/organizations",
        "/api/v1/admin/devices",
    ],
)
async def test_new_rbac_routes_require_authentication(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(path)
    assert response.status_code == 401
