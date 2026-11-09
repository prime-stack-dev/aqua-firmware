"""Turns readings into alerts. Each decision is a small function on its own."""
import operator
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertRule
from app.models.enums import AlertKind, AlertState, RuleOperator, Severity
from app.repositories.alert import AlertRepository
from app.services.domain import DeviceRef, Reading, ReferenceData

DEFAULT_CLEAR_AFTER = 3

_SEVERITY_RANK = {Severity.LOW: 1, Severity.CRITICAL: 2}
_COMPARE = {
    RuleOperator.LT: operator.lt,
    RuleOperator.LTE: operator.le,
    RuleOperator.GT: operator.gt,
    RuleOperator.GTE: operator.ge,
}


def _specificity(rule: AlertRule, device: DeviceRef) -> int | None:
    """How closely a rule targets a device, or None if it does not apply."""
    if rule.pond_id is not None:
        return 3 if rule.pond_id == device.pond_id else None
    if rule.farm_id is not None:
        return 2 if rule.farm_id == device.farm_id else None
    if rule.org_id is not None:
        return 1 if rule.org_id == device.org_id else None
    return 0


def rules_for_device(
    rules: Sequence[AlertRule], device: DeviceRef
) -> dict[str, list[AlertRule]]:
    """Enabled rules per metric, keeping the most specific per severity.

    A disabled rule still wins over a broader one, so a customer can switch
    off a platform default.
    """
    chosen: dict[tuple[str, str], tuple[int, AlertRule]] = {}
    for rule in rules:
        rank = _specificity(rule, device)
        if rank is None:
            continue
        key = (rule.metric, rule.severity)
        if key not in chosen or rank > chosen[key][0]:
            chosen[key] = (rank, rule)

    by_metric: dict[str, list[AlertRule]] = defaultdict(list)
    for _, rule in chosen.values():
        if rule.enabled:
            by_metric[rule.metric].append(rule)
    return dict(by_metric)


def worst_breach(rules: Sequence[AlertRule], value: float) -> AlertRule | None:
    breached = [r for r in rules if _COMPARE[RuleOperator(r.operator)](value, r.threshold)]
    return max(breached, key=lambda r: _SEVERITY_RANK[Severity(r.severity)], default=None)


def open_alert(reading: Reading, metric: str, rule: AlertRule, value: float) -> Alert:
    return Alert(
        id=uuid.uuid4(),
        org_id=reading.device.org_id,
        pond_id=reading.device.pond_id,
        device_id=reading.device.id,
        rule_id=rule.id,
        kind=AlertKind.THRESHOLD,
        metric=metric,
        severity=rule.severity,
        state=AlertState.OPEN,
        threshold=rule.threshold,
        last_value=value,
        ok_streak=0,
        opened_at=reading.ts,
    )


def advance_alert(
    alert: Alert, breach: AlertRule | None, value: float, ts: datetime, clear_after: int
) -> None:
    """Apply one reading to a live alert.

    Getting worse takes effect at once. Getting better needs `clear_after`
    readings in a row, so a value near a limit does not flap.
    """
    alert.last_value = value
    current = _SEVERITY_RANK[Severity(breach.severity)] if breach else 0
    alert_rank = _SEVERITY_RANK[Severity(alert.severity)]

    if current >= alert_rank:
        alert.ok_streak = 0
        if current > alert_rank:
            alert.severity = breach.severity
            alert.threshold = breach.threshold
            alert.rule_id = breach.id
            alert.state = AlertState.OPEN
            alert.acknowledged_at = None
            alert.acknowledged_by = None
        return

    alert.ok_streak += 1
    if alert.ok_streak < clear_after:
        return
    alert.ok_streak = 0
    if breach is None:
        alert.state = AlertState.CLOSED
        alert.closed_at = ts
    else:
        alert.severity = breach.severity
        alert.threshold = breach.threshold
        alert.rule_id = breach.id


def _row(alert: Alert) -> dict:
    return {column.name: getattr(alert, column.name) for column in Alert.__table__.columns}


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alerts = AlertRepository(session)

    async def process(
        self, readings: Sequence[Reading], reference: ReferenceData, now: datetime
    ) -> None:
        """Readings must be new for their device and sorted by time."""
        device_ids = list({r.device.id for r in readings})
        live: dict[uuid.UUID, dict[str, Alert]] = defaultdict(dict)
        for alert in await self.alerts.live_threshold_alerts(device_ids):
            live[alert.device_id][alert.metric] = alert

        created: list[Alert] = []
        rules_cache: dict[uuid.UUID, dict[str, list[AlertRule]]] = {}
        defaults = reference.rules_by_org.get(None, [])

        for reading in readings:
            device = reading.device
            if device.id not in rules_cache:
                candidates = defaults + reference.rules_by_org.get(device.org_id, [])
                rules_cache[device.id] = rules_for_device(candidates, device)
            rules = rules_cache[device.id]
            device_alerts = live[device.id]

            for metric in set(rules) | set(device_alerts):
                value = reading.value(metric)
                if value is None:
                    continue
                metric_rules = rules.get(metric, [])
                breach = worst_breach(metric_rules, value)
                alert = device_alerts.get(metric)
                if alert is None:
                    if breach is not None:
                        alert = open_alert(reading, metric, breach, value)
                        device_alerts[metric] = alert
                        created.append(alert)
                    continue
                clear_after = max(
                    (r.clear_after for r in metric_rules), default=DEFAULT_CLEAR_AFTER
                )
                advance_alert(alert, breach, value, reading.ts, clear_after)
                if alert.state == AlertState.CLOSED:
                    del device_alerts[metric]

        await self.session.flush()
        if created:
            await self.alerts.insert_threshold_alerts([_row(alert) for alert in created])
        await self.alerts.close_no_data_alerts(device_ids, now)
