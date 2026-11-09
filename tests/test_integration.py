"""End-to-end checks against a real PostgreSQL."""
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Alert,
    Device,
    DeviceLatest,
    Farm,
    Membership,
    Organization,
    Plan,
    Pond,
    Subscription,
    Telemetry,
    User,
)
from app.models.enums import AlertState, PondStatus, Role
from app.services.ingest import IngestService
from app.services.maintenance import ensure_partitions, run_health_check

pytestmark = pytest.mark.db

PASSWORD = "test-password"
API = "/api/v1"


@dataclass
class Tenant:
    org_id: uuid.UUID
    farm_id: uuid.UUID
    pond_id: uuid.UUID
    device_id: uuid.UUID
    serial: str
    subscription_id: uuid.UUID
    headers: dict[str, str]
    viewer_headers: dict[str, str]


async def login(client, email: str) -> dict:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


async def make_tenant(client, sessions, slug: str, ends_in_days: int = 30) -> Tenant:
    now = datetime.now(UTC)
    password_hash = hash_password(PASSWORD)
    async with sessions() as session:
        plan = await session.scalar(select(Plan).where(Plan.name == "Test"))
        if plan is None:
            plan = Plan(name="Test")
            session.add(plan)
        org = Organization(name=slug, slug=slug)
        owner = User(email=f"owner@{slug}.com", full_name="Owner", password_hash=password_hash)
        viewer = User(email=f"viewer@{slug}.com", full_name="Viewer", password_hash=password_hash)
        session.add_all([org, owner, viewer])
        await session.flush()
        session.add_all(
            [
                Membership(user_id=owner.id, org_id=org.id, role=Role.OWNER),
                Membership(user_id=viewer.id, org_id=org.id, role=Role.VIEWER),
            ]
        )
        farm = Farm(org_id=org.id, name="Farm")
        session.add(farm)
        await session.flush()
        pond = Pond(org_id=org.id, farm_id=farm.id, name="Pond")
        session.add(pond)
        await session.flush()
        device = Device(serial=f"SN-{slug}", org_id=org.id, pond_id=pond.id)
        session.add(device)
        await session.flush()
        subscription = Subscription(
            org_id=org.id,
            device_id=device.id,
            plan_id=plan.id,
            starts_at=now - timedelta(days=60),
            ends_at=now + timedelta(days=ends_in_days),
        )
        session.add(subscription)
        await session.commit()

    owner_token = (await login(client, f"owner@{slug}.com"))["access_token"]
    viewer_token = (await login(client, f"viewer@{slug}.com"))["access_token"]
    return Tenant(
        org.id, farm.id, pond.id, device.id, device.serial, subscription.id,
        {"Authorization": f"Bearer {owner_token}"},
        {"Authorization": f"Bearer {viewer_token}"},
    )


async def make_service(sessions) -> IngestService:
    service = IngestService(sessions, get_settings())
    await service.refresh_reference()
    return service


def publish(service: IngestService, serial: str, ts: datetime, **metrics) -> None:
    body = json.dumps({"ts": ts.isoformat(), **metrics}).encode()
    service.handle_message(f"aqua/devices/{serial}/telemetry", body)


async def drain(service: IngestService) -> None:
    while await service.flush():
        pass


async def pond_status(sessions, pond_id) -> str:
    async with sessions() as session:
        return await session.scalar(select(Pond.status).where(Pond.id == pond_id))


async def live_alerts(sessions, device_id) -> list[Alert]:
    async with sessions() as session:
        rows = await session.scalars(
            select(Alert).where(Alert.device_id == device_id, Alert.state != AlertState.CLOSED)
        )
        return list(rows)


async def test_login_rejects_wrong_password(client, sessions):
    await make_tenant(client, sessions, "alpha")
    response = await client.post(
        f"{API}/auth/login", json={"email": "owner@alpha.com", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_refresh_token_rotates_and_reuse_ends_all_sessions(client, sessions):
    await make_tenant(client, sessions, "alpha")
    first = await login(client, "owner@alpha.com")

    rotated = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200

    reused = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert reused.status_code == 401

    latest = rotated.json()["refresh_token"]
    after = await client.post(f"{API}/auth/refresh", json={"refresh_token": latest})
    assert after.status_code == 401


async def test_customers_cannot_see_each_other(client, sessions):
    a = await make_tenant(client, sessions, "alpha")
    b = await make_tenant(client, sessions, "beta")
    service = await make_service(sessions)
    publish(service, b.serial, datetime.now(UTC), dissolved_oxygen=3.0)
    await drain(service)
    async with sessions() as session:
        b_alert = await session.scalar(select(Alert.id).where(Alert.device_id == b.device_id))

    for path in (
        f"/farms/{b.farm_id}/dashboard",
        f"/ponds/{b.pond_id}",
        f"/telemetry/{b.device_id}/latest",
        f"/telemetry/{b.device_id}/history",
    ):
        response = await client.get(f"{API}{path}", headers=a.headers)
        assert response.status_code == 404, path

    ack = await client.post(f"{API}/alerts/{b_alert}/acknowledge", headers=a.headers)
    assert ack.status_code == 404

    for path, key in (("/farms", b.farm_id), ("/ponds", b.pond_id), ("/devices", b.device_id)):
        response = await client.get(f"{API}{path}", headers=a.headers)
        assert str(key) not in response.text, path

    assert (await client.get(f"{API}/alerts", headers=a.headers)).json() == []
    subscriptions = await client.get(f"{API}/subscriptions", headers=a.headers)
    assert str(b.subscription_id) not in subscriptions.text


async def test_reading_flows_to_the_dashboard(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    publish(service, tenant.serial, datetime.now(UTC), dissolved_oxygen=6.2, turbidity=3.5)
    await drain(service)

    assert await pond_status(sessions, tenant.pond_id) == PondStatus.OK
    latest = await client.get(f"{API}/telemetry/{tenant.device_id}/latest", headers=tenant.headers)
    assert latest.status_code == 200
    assert latest.json()["dissolved_oxygen"] == 6.2
    assert latest.json()["extra"] == {"turbidity": 3.5}

    dashboard = await client.get(f"{API}/farms/{tenant.farm_id}/dashboard", headers=tenant.headers)
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["summary"]["ponds_in_range"] == 1
    assert body["summary"]["median_dissolved_oxygen"] == 6.2
    assert body["ponds"][0]["dissolved_oxygen"] == 6.2


async def test_duplicate_message_is_stored_once(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    ts = datetime.now(UTC)
    publish(service, tenant.serial, ts, dissolved_oxygen=3.0)
    await drain(service)
    publish(service, tenant.serial, ts, dissolved_oxygen=3.0)
    publish(service, tenant.serial, ts, dissolved_oxygen=3.0)
    await drain(service)

    async with sessions() as session:
        rows = await session.scalars(select(Telemetry).where(Telemetry.device_id == tenant.device_id))
        assert len(rows.all()) == 1
    assert len(await live_alerts(sessions, tenant.device_id)) == 1


async def test_default_limits_raise_low_and_critical_then_clear(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    start = datetime.now(UTC) - timedelta(minutes=10)

    publish(service, tenant.serial, start, dissolved_oxygen=4.7)
    await drain(service)
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.LOW

    publish(service, tenant.serial, start + timedelta(minutes=1), dissolved_oxygen=3.8)
    await drain(service)
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.CRITICAL_ALERT
    alerts = await live_alerts(sessions, tenant.device_id)
    assert [a.severity for a in alerts] == ["critical"]

    for minute in range(2, 5):
        publish(service, tenant.serial, start + timedelta(minutes=minute), dissolved_oxygen=6.0)
        await drain(service)
    assert await live_alerts(sessions, tenant.device_id) == []
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.OK


async def test_delayed_reading_is_stored_but_does_not_alert(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    now = datetime.now(UTC)
    publish(service, tenant.serial, now, dissolved_oxygen=6.0)
    await drain(service)
    publish(service, tenant.serial, now - timedelta(minutes=5), dissolved_oxygen=2.0)
    await drain(service)

    async with sessions() as session:
        latest = await session.get(DeviceLatest, tenant.device_id)
        assert latest.dissolved_oxygen == 6.0
        rows = await session.scalars(select(Telemetry).where(Telemetry.device_id == tenant.device_id))
        assert len(rows.all()) == 2
    assert await live_alerts(sessions, tenant.device_id) == []


async def test_silent_device_marks_pond_no_data_and_recovers(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    now = datetime.now(UTC)
    publish(service, tenant.serial, now - timedelta(minutes=9), dissolved_oxygen=6.0)
    await drain(service)

    async with sessions() as session:
        assert await run_health_check(session, now) == 1
        await session.commit()
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.NO_DATA
    assert [a.kind for a in await live_alerts(sessions, tenant.device_id)] == ["no_data"]

    dashboard = await client.get(f"{API}/farms/{tenant.farm_id}/dashboard", headers=tenant.headers)
    assert dashboard.json()["ponds"][0]["dissolved_oxygen"] is None

    publish(service, tenant.serial, now, dissolved_oxygen=6.0)
    await drain(service)
    assert await live_alerts(sessions, tenant.device_id) == []
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.OK


async def test_grace_period_keeps_access(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha", ends_in_days=-3)
    service = await make_service(sessions)
    publish(service, tenant.serial, datetime.now(UTC), dissolved_oxygen=6.0)
    await drain(service)
    response = await client.get(f"{API}/telemetry/{tenant.device_id}/latest", headers=tenant.headers)
    assert response.status_code == 200


async def test_after_grace_data_is_stored_but_locked(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha", ends_in_days=-8)
    service = await make_service(sessions)
    now = datetime.now(UTC)
    publish(service, tenant.serial, now, dissolved_oxygen=3.0)
    await drain(service)

    async with sessions() as session:
        stored = await session.scalar(select(Telemetry).where(Telemetry.device_id == tenant.device_id))
        assert stored is not None

    locked = await client.get(f"{API}/telemetry/{tenant.device_id}/latest", headers=tenant.headers)
    assert locked.status_code == 403
    assert (await client.get(f"{API}/alerts", headers=tenant.headers)).json() == []
    assert await pond_status(sessions, tenant.pond_id) == PondStatus.SUBSCRIPTION_EXPIRED
    dashboard = await client.get(f"{API}/farms/{tenant.farm_id}/dashboard", headers=tenant.headers)
    assert dashboard.json()["ponds"][0]["dissolved_oxygen"] is None


async def test_history_returns_hourly_averages_for_long_ranges(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    now = datetime.now(UTC).replace(minute=30, second=0, microsecond=0) - timedelta(hours=2)
    publish(service, tenant.serial, now, dissolved_oxygen=6.0)
    publish(service, tenant.serial, now + timedelta(minutes=10), dissolved_oxygen=7.0)
    await drain(service)

    response = await client.get(
        f"{API}/telemetry/{tenant.device_id}/history",
        headers=tenant.headers,
        params={"start": (now - timedelta(days=5)).isoformat(), "end": datetime.now(UTC).isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolution"] == "hour"
    assert body["points"][0]["dissolved_oxygen"] == 6.5


async def test_customer_rule_overrides_default_and_is_owner_only(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    rule = {"metric": "dissolved_oxygen", "operator": "lt", "threshold": 3.0, "severity": "critical"}

    denied = await client.post(f"{API}/alert-rules", json=rule, headers=tenant.viewer_headers)
    assert denied.status_code == 403
    created = await client.post(f"{API}/alert-rules", json=rule, headers=tenant.headers)
    assert created.status_code == 201, created.text
    duplicate = await client.post(f"{API}/alert-rules", json=rule, headers=tenant.headers)
    assert duplicate.status_code == 409

    service = await make_service(sessions)
    publish(service, tenant.serial, datetime.now(UTC), dissolved_oxygen=3.8)
    await drain(service)
    assert [a.severity for a in await live_alerts(sessions, tenant.device_id)] == ["low"]


async def test_platform_default_rules_are_read_only(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    rules = (await client.get(f"{API}/alert-rules", headers=tenant.headers)).json()
    default = next(r for r in rules if r["org_id"] is None)
    response = await client.put(
        f"{API}/alert-rules/{default['id']}", json={"threshold": 1.0}, headers=tenant.headers
    )
    assert response.status_code == 404


async def test_viewer_cannot_acknowledge_but_owner_can(client, sessions):
    tenant = await make_tenant(client, sessions, "alpha")
    service = await make_service(sessions)
    publish(service, tenant.serial, datetime.now(UTC), dissolved_oxygen=3.0)
    await drain(service)
    alert_id = (await client.get(f"{API}/alerts", headers=tenant.headers)).json()[0]["id"]

    denied = await client.post(
        f"{API}/alerts/{alert_id}/acknowledge", headers=tenant.viewer_headers
    )
    assert denied.status_code == 403
    done = await client.post(f"{API}/alerts/{alert_id}/acknowledge", headers=tenant.headers)
    assert done.status_code == 200
    assert done.json()["state"] == "acknowledged"


async def test_partition_job_is_repeatable(sessions):
    now = datetime.now(UTC)
    async with sessions() as session:
        await ensure_partitions(session, now)
        await ensure_partitions(session, now)
        await session.commit()
        count = await session.scalar(
            text("SELECT count(*) FROM pg_inherits WHERE inhparent = 'telemetry'::regclass")
        )
    assert count >= 5
