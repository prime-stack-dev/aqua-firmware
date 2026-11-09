import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Device, DeviceLatest, Pond
from app.models.enums import AlertKind, AlertState, PondStatus, Severity
from app.repositories.subscription import accessible_device_ids


@dataclass(frozen=True)
class DeviceHealth:
    has_access: bool
    is_fresh: bool
    severity: Severity | None


def derive_pond_status(devices: Sequence[DeviceHealth]) -> PondStatus:
    """Worst condition wins. Missing data is never treated as safe."""
    if not devices:
        return PondStatus.UNKNOWN
    visible = [d for d in devices if d.has_access]
    if not visible:
        return PondStatus.SUBSCRIPTION_EXPIRED
    if any(d.severity == Severity.CRITICAL for d in visible):
        return PondStatus.CRITICAL_ALERT
    if not all(d.is_fresh for d in visible):
        return PondStatus.NO_DATA
    if any(d.severity == Severity.LOW for d in visible):
        return PondStatus.LOW
    return PondStatus.OK


class PondStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recompute(
        self,
        now: datetime,
        offline_minutes: int,
        pond_ids: Collection[uuid.UUID] | None = None,
    ) -> None:
        """Refresh stored pond status, for the given ponds or for all of them."""
        ponds_stmt = select(Pond.id, Pond.status)
        devices_stmt = (
            select(
                Device.id,
                Device.pond_id,
                DeviceLatest.ts,
                Device.id.in_(accessible_device_ids(now)).label("has_access"),
            )
            .outerjoin(DeviceLatest, DeviceLatest.device_id == Device.id)
            .where(Device.pond_id.is_not(None))
        )
        alerts_stmt = select(Alert.device_id, Alert.severity).where(
            Alert.kind == AlertKind.THRESHOLD, Alert.state != AlertState.CLOSED
        )
        if pond_ids is not None:
            ponds_stmt = ponds_stmt.where(Pond.id.in_(pond_ids))
            devices_stmt = devices_stmt.where(Device.pond_id.in_(pond_ids))
            alerts_stmt = alerts_stmt.where(
                Alert.device_id.in_(select(Device.id).where(Device.pond_id.in_(pond_ids)))
            )

        ponds = (await self.session.execute(ponds_stmt)).all()
        devices = (await self.session.execute(devices_stmt)).all()
        alerts = (await self.session.execute(alerts_stmt)).all()

        worst: dict[uuid.UUID, Severity] = {}
        for device_id, severity in alerts:
            if worst.get(device_id) != Severity.CRITICAL:
                worst[device_id] = Severity(severity)

        cutoff = now - timedelta(minutes=offline_minutes)
        health: dict[uuid.UUID, list[DeviceHealth]] = defaultdict(list)
        for device_id, pond_id, ts, has_access in devices:
            health[pond_id].append(
                DeviceHealth(
                    has_access=has_access,
                    is_fresh=ts is not None and ts >= cutoff,
                    severity=worst.get(device_id),
                )
            )

        changes: dict[PondStatus, list[uuid.UUID]] = defaultdict(list)
        for pond_id, current in ponds:
            status = derive_pond_status(health.get(pond_id, []))
            if status != current:
                changes[status].append(pond_id)

        for status, changed in changes.items():
            await self.session.execute(
                update(Pond)
                .where(Pond.id.in_(changed))
                .values(status=status)
                .execution_options(synchronize_session=False)
            )
