"""Checks that need no database."""
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.telemetry import pick_resolution
from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.models import Plan, Subscription
from app.models.enums import SubscriptionState
from app.repositories.subscription import accessible_device_ids
from app.services.domain import DeviceRef, Reading
from app.services.ingest import IngestService
from app.services.subscriptions import subscription_state

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def test_password_round_trip():
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("anything", None)


def test_access_token_round_trip():
    user, org = uuid.uuid4(), uuid.uuid4()
    assert decode_access_token(create_access_token(user, org)) == (user, org)
    assert decode_access_token(create_access_token(user, None)) == (user, None)


def test_tampered_token_is_rejected():
    token = create_access_token(uuid.uuid4(), None)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token[:-2] + "xx")


@pytest.mark.parametrize(
    ("days_after_end", "expected"),
    [
        (-1, SubscriptionState.ACTIVE),
        (1, SubscriptionState.GRACE),
        (7, SubscriptionState.GRACE),
        (8, SubscriptionState.EXPIRED),
    ],
)
def test_subscription_state(days_after_end, expected):
    subscription = Subscription(
        status="active",
        starts_at=NOW - timedelta(days=30),
        ends_at=NOW - timedelta(days=days_after_end),
    )
    assert subscription_state(subscription, Plan(grace_days=7), NOW) == expected


def test_canceled_subscription_has_no_grace():
    subscription = Subscription(
        status="canceled", starts_at=NOW - timedelta(days=30), ends_at=NOW + timedelta(days=30)
    )
    assert subscription_state(subscription, Plan(grace_days=7), NOW) == SubscriptionState.CANCELED


def test_history_resolution():
    assert pick_resolution(NOW - timedelta(hours=48), NOW) == "raw"
    assert pick_resolution(NOW - timedelta(days=60), NOW) == "hour"
    assert pick_resolution(NOW - timedelta(days=61), NOW) == "day"


def test_access_query_reads_its_own_device_table():
    sql = str(accessible_device_ids(NOW).compile(dialect=postgresql.asyncpg.dialect()))
    assert "JOIN devices" in sql
    assert "make_interval" in sql


def reading(number: int) -> Reading:
    device = DeviceRef(uuid.uuid4(), uuid.uuid4(), None, None)
    return Reading(device, NOW + timedelta(seconds=number), NOW, {"ph": 7.0})


class FlakyIngest(IngestService):
    def __init__(self) -> None:
        super().__init__(None, get_settings())
        self.fail = False
        self.saved: list[Reading] = []

    async def _persist(self, batch) -> None:
        if self.fail:
            raise ConnectionError("database down")
        self.saved.extend(batch)


async def test_batch_stays_in_buffer_when_database_is_down():
    service = FlakyIngest()
    service._buffer.extend(reading(n) for n in range(3))
    expected = list(service._buffer)

    service.fail = True
    with pytest.raises(ConnectionError):
        await service.flush()
    assert list(service._buffer) == expected

    service.fail = False
    assert await service.flush() == 3
    assert service.saved == expected
    assert not service._buffer


async def test_flush_respects_batch_size():
    service = FlakyIngest()
    service.reference.settings = {"ingest_batch_size": 2}
    service._buffer.extend(reading(n) for n in range(3))
    assert await service.flush() == 2
    assert await service.flush() == 1
    assert await service.flush() == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/me",
        "/api/v1/farms",
        "/api/v1/ponds",
        "/api/v1/devices",
        "/api/v1/alerts",
        "/api/v1/alert-rules",
        "/api/v1/subscriptions",
        f"/api/v1/ponds/{uuid.uuid4()}",
        f"/api/v1/farms/{uuid.uuid4()}/dashboard",
        f"/api/v1/telemetry/{uuid.uuid4()}/latest",
        f"/api/v1/telemetry/{uuid.uuid4()}/history",
    ],
)
async def test_every_route_needs_a_login(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(path)
    assert response.status_code == 401
