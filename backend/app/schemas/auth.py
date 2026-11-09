import uuid

from pydantic import BaseModel, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    # Only needed when the user belongs to more than one organization.
    organization_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OrganizationAccess(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Role


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_platform_admin: bool
    current_organization_id: uuid.UUID | None
    organizations: list[OrganizationAccess]
