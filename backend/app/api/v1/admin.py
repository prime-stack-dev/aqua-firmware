from fastapi import APIRouter

from app.api.v1.deps import Limit, Offset, PlatformAdminDep, SessionDep, utc_now
from app.repositories.admin import PlatformAdminRepository
from app.schemas.admin import AdminDeviceOut, AdminOrganizationOut, PlatformOverviewOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=PlatformOverviewOut)
async def platform_overview(_admin: PlatformAdminDep, session: SessionDep) -> PlatformOverviewOut:
    """Global system status across all customer tenants (Platform Admin only)."""
    now = utc_now()
    stats = await PlatformAdminRepository(session).overview(now)
    return PlatformOverviewOut(**stats)


@router.get("/organizations", response_model=list[AdminOrganizationOut])
async def list_organizations(
    _admin: PlatformAdminDep,
    session: SessionDep,
    limit: Limit = 100,
    offset: Offset = 0,
) -> list[AdminOrganizationOut]:
    """List all organizations with tenant resource metrics (Platform Admin only)."""
    rows = await PlatformAdminRepository(session).list_organizations(limit, offset)
    return [
        AdminOrganizationOut(
            id=org.id,
            name=org.name,
            slug=org.slug,
            members_count=members_count,
            farms_count=farms_count,
            ponds_count=ponds_count,
            devices_count=devices_count,
            created_at=org.created_at,
        )
        for org, members_count, farms_count, ponds_count, devices_count in rows
    ]


@router.get("/devices", response_model=list[AdminDeviceOut])
async def list_all_devices(
    _admin: PlatformAdminDep,
    session: SessionDep,
    limit: Limit = 100,
    offset: Offset = 0,
) -> list[AdminDeviceOut]:
    """List all hardware devices across all customers (Platform Admin only)."""
    now = utc_now()
    rows = await PlatformAdminRepository(session).list_all_devices(now, limit, offset)
    return [
        AdminDeviceOut(
            id=device.id,
            serial=device.serial,
            name=device.name,
            is_active=device.is_active,
            org_id=device.org_id,
            org_name=org_name,
            pond_id=device.pond_id,
            pond_name=pond_name,
            last_reading_at=last_reading_at,
            has_access=has_access,
        )
        for device, org_name, pond_name, last_reading_at, has_access in rows
    ]
