import uuid
from typing import Annotated

from fastapi import APIRouter

from app.api.v1.deps import Limit, MemberDep, Offset, SessionDep, tenant_repo, utc_now
from app.core.errors import not_found
from app.repositories.device import DeviceRepository
from app.repositories.farm import FarmRepository, PondRepository
from app.schemas.resources import DashboardOut, DeviceOut, FarmOut, PondDetail, PondOut
from app.services.dashboard import DashboardService

router = APIRouter(tags=["farms"])

Farms = Annotated[FarmRepository, tenant_repo(FarmRepository)]
Ponds = Annotated[PondRepository, tenant_repo(PondRepository)]
Devices = Annotated[DeviceRepository, tenant_repo(DeviceRepository)]


@router.get("/farms", response_model=list[FarmOut])
async def list_farms(farms: Farms, limit: Limit = 100, offset: Offset = 0):
    return await farms.list(limit, offset)


@router.get("/farms/{farm_id}/dashboard", response_model=DashboardOut)
async def farm_dashboard(farm_id: uuid.UUID, member: MemberDep, session: SessionDep):
    return await DashboardService(session, member.org_id).farm_dashboard(farm_id, utc_now())


@router.get("/ponds", response_model=list[PondOut])
async def list_ponds(
    ponds: Ponds, farm_id: uuid.UUID | None = None, limit: Limit = 100, offset: Offset = 0
):
    if farm_id is not None and not await FarmRepository(ponds.session, ponds.org_id).get(farm_id):
        raise not_found("Farm")
    return await ponds.list_for(farm_id, limit, offset)


@router.get("/ponds/{pond_id}", response_model=PondDetail)
async def get_pond(pond_id: uuid.UUID, member: MemberDep, session: SessionDep):
    return await DashboardService(session, member.org_id).pond_detail(pond_id, utc_now())


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(devices: Devices, limit: Limit = 100, offset: Offset = 0):
    rows = await devices.list_with_status(utc_now(), limit, offset)
    return [
        DeviceOut(
            id=device.id,
            serial=device.serial,
            name=device.name,
            pond_id=device.pond_id,
            last_reading_at=last_reading_at,
            has_access=has_access,
        )
        for device, last_reading_at, has_access in rows
    ]
