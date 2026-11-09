import uuid
from datetime import UTC, datetime

from app.models import Alert, AlertRule
from app.models.enums import AlertKind, AlertState, PondStatus, Severity
from app.services.alerts import advance_alert, rules_for_device, worst_breach
from app.services.domain import DeviceRef
from app.services.pond_status import DeviceHealth, derive_pond_status

TS = datetime(2026, 11, 8, tzinfo=UTC)
ORG, FARM, POND = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
DEVICE = DeviceRef(uuid.uuid4(), ORG, POND, FARM)


def rule(threshold, severity="critical", enabled=True, **scope) -> AlertRule:
    return AlertRule(
        id=uuid.uuid4(),
        metric="dissolved_oxygen",
        operator="lt",
        threshold=threshold,
        severity=severity,
        clear_after=3,
        enabled=enabled,
        org_id=scope.get("org_id"),
        farm_id=scope.get("farm_id"),
        pond_id=scope.get("pond_id"),
    )


CRITICAL = rule(4.0)
LOW = rule(5.0, "low")
RULES = [CRITICAL, LOW]


def alert(severity="low", state=AlertState.OPEN) -> Alert:
    return Alert(
        kind=AlertKind.THRESHOLD,
        metric="dissolved_oxygen",
        severity=severity,
        state=state,
        ok_streak=0,
    )


def effective_threshold(rules) -> float:
    return rules_for_device(rules, DEVICE)["dissolved_oxygen"][0].threshold


def test_breach_picks_worst_severity():
    assert worst_breach(RULES, 3.8) is CRITICAL
    assert worst_breach(RULES, 4.7) is LOW
    assert worst_breach(RULES, 5.0) is None


def test_limit_itself_is_not_a_breach_for_less_than():
    assert worst_breach(RULES, 4.0) is LOW


def test_most_specific_rule_wins():
    default = rule(4.0)
    org_rule = rule(3.5, org_id=ORG)
    farm_rule = rule(3.2, org_id=ORG, farm_id=FARM)
    pond_rule = rule(3.0, org_id=ORG, pond_id=POND)
    assert effective_threshold([default]) == 4.0
    assert effective_threshold([default, org_rule]) == 3.5
    assert effective_threshold([org_rule, default, farm_rule]) == 3.2
    assert effective_threshold([pond_rule, farm_rule, org_rule, default]) == 3.0


def test_rules_for_other_scopes_do_not_apply():
    other_org = rule(1.0, org_id=uuid.uuid4())
    other_pond = rule(2.0, org_id=ORG, pond_id=uuid.uuid4())
    assert effective_threshold([rule(4.0), other_org, other_pond]) == 4.0


def test_disabled_override_switches_off_the_default():
    disabled = rule(3.0, enabled=False, org_id=ORG)
    assert rules_for_device([rule(4.0), disabled], DEVICE) == {}


def test_worsening_escalates_immediately_and_reopens():
    live = alert("low", AlertState.ACKNOWLEDGED)
    live.acknowledged_at = TS
    advance_alert(live, CRITICAL, 3.5, TS, 3)
    assert live.severity == "critical"
    assert live.state == AlertState.OPEN
    assert live.acknowledged_at is None
    assert live.threshold == 4.0


def test_alert_closes_only_after_enough_good_readings():
    live = alert()
    advance_alert(live, None, 6.0, TS, 3)
    advance_alert(live, None, 6.0, TS, 3)
    assert live.state == AlertState.OPEN
    advance_alert(live, None, 6.0, TS, 3)
    assert live.state == AlertState.CLOSED
    assert live.closed_at == TS


def test_a_bad_reading_resets_the_recovery_count():
    live = alert()
    advance_alert(live, None, 6.0, TS, 3)
    advance_alert(live, None, 6.0, TS, 3)
    advance_alert(live, LOW, 4.5, TS, 3)
    advance_alert(live, None, 6.0, TS, 3)
    advance_alert(live, None, 6.0, TS, 3)
    assert live.state == AlertState.OPEN


def test_critical_steps_down_to_low_after_recovery():
    live = alert("critical")
    for _ in range(3):
        advance_alert(live, LOW, 4.5, TS, 3)
    assert live.severity == "low"
    assert live.state == AlertState.OPEN
    assert live.ok_streak == 0


def health(has_access=True, is_fresh=True, severity=None) -> DeviceHealth:
    return DeviceHealth(has_access, is_fresh, severity)


def test_pond_status_order():
    assert derive_pond_status([]) == PondStatus.UNKNOWN
    assert derive_pond_status([health()]) == PondStatus.OK
    assert derive_pond_status([health(severity=Severity.LOW)]) == PondStatus.LOW
    assert derive_pond_status([health(is_fresh=False)]) == PondStatus.NO_DATA
    assert (
        derive_pond_status([health(severity=Severity.CRITICAL), health(is_fresh=False)])
        == PondStatus.CRITICAL_ALERT
    )
    assert derive_pond_status([health(severity=Severity.LOW), health(is_fresh=False)]) == (
        PondStatus.NO_DATA
    )


def test_expired_devices_are_ignored_when_another_has_access():
    expired = health(has_access=False, severity=Severity.CRITICAL)
    assert derive_pond_status([expired, health()]) == PondStatus.OK
    assert derive_pond_status([expired]) == PondStatus.SUBSCRIPTION_EXPIRED
