import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.models import Alert, AlertRule, MetricDefinition
from app.models.enums import AlertKind, AlertState
from app.repositories.base import BaseRepository, TenantRepository
from app.repositories.subscription import accessible_device_ids


class AlertRepository(BaseRepository[Alert]):
    """Writes from the workers. Not for customer-facing code."""

    model = Alert

    async def live_threshold_alerts(self, device_ids: Sequence[uuid.UUID]) -> Sequence[Alert]:
        stmt = select(Alert).where(
            Alert.device_id.in_(device_ids),
            Alert.kind == AlertKind.THRESHOLD,
            Alert.state != AlertState.CLOSED,
        )
        return (await self.session.scalars(stmt)).all()

    async def insert_threshold_alerts(self, rows: Sequence[dict]) -> None:
        stmt = insert(Alert).values(rows).on_conflict_do_nothing(
            index_elements=["device_id", "metric"],
            index_where=text("kind = 'threshold' AND state <> 'closed'"),
        )
        await self.session.execute(stmt)

    async def insert_no_data_alerts(self, rows: Sequence[dict]) -> None:
        stmt = insert(Alert).values(rows).on_conflict_do_nothing(
            index_elements=["device_id"],
            index_where=text("kind = 'no_data' AND state <> 'closed'"),
        )
        await self.session.execute(stmt)

    async def close_no_data_alerts(
        self, device_ids: Sequence[uuid.UUID], now: datetime
    ) -> None:
        await self.session.execute(
            update(Alert)
            .where(
                Alert.device_id.in_(device_ids),
                Alert.kind == AlertKind.NO_DATA,
                Alert.state != AlertState.CLOSED,
            )
            .values(state=AlertState.CLOSED, closed_at=now)
            .execution_options(synchronize_session=False)
        )


class TenantAlertRepository(TenantRepository[Alert]):
    model = Alert

    def _visible(self, now: datetime):
        return self._select().where(
            Alert.device_id.in_(accessible_device_ids(now, self.org_id))
        )

    async def list_visible(
        self, now: datetime, state: AlertState | None, limit: int, offset: int
    ) -> Sequence[Alert]:
        stmt = self._visible(now).order_by(Alert.opened_at.desc()).limit(limit).offset(offset)
        if state is not None:
            stmt = stmt.where(Alert.state == state)
        return (await self.session.scalars(stmt)).all()

    async def get_visible(self, alert_id: uuid.UUID, now: datetime) -> Alert | None:
        return await self.session.scalar(self._visible(now).where(Alert.id == alert_id))

    async def count_live_for_ponds(
        self, pond_ids: Sequence[uuid.UUID], now: datetime
    ) -> int:
        stmt = self._visible(now).where(
            Alert.pond_id.in_(pond_ids), Alert.state != AlertState.CLOSED
        )
        return await self.session.scalar(select(func.count()).select_from(stmt.subquery()))


class TenantAlertRuleRepository(TenantRepository[AlertRule]):
    """The organization's own rules. Platform defaults are read-only here."""

    model = AlertRule

    async def list_with_defaults(self) -> Sequence[AlertRule]:
        stmt = (
            select(AlertRule)
            .where(or_(AlertRule.org_id == self.org_id, AlertRule.org_id.is_(None)))
            .order_by(AlertRule.metric, AlertRule.severity)
        )
        return (await self.session.scalars(stmt)).all()

    async def metric_exists(self, key: str) -> bool:
        return await self.session.get(MetricDefinition, key) is not None
