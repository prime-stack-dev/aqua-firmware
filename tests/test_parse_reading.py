import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.services.domain import DeviceRef, ReferenceData
from app.services.ingest import RejectedReading, parse_reading

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
TOPIC = "aqua/devices/SN1/telemetry"
DEVICE = DeviceRef(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
REFERENCE = ReferenceData(
    devices={"SN1": DEVICE},
    metric_limits={"dissolved_oxygen": (0, 25), "ph": (0, 14)},
)


def payload(**fields) -> bytes:
    return json.dumps({"ts": NOW.isoformat(), **fields}).encode()


def parse(body: bytes, topic: str = TOPIC):
    return parse_reading(topic, body, REFERENCE, get_settings(), NOW)


def rejected_reason(body: bytes, topic: str = TOPIC) -> str:
    with pytest.raises(RejectedReading) as caught:
        parse(body, topic)
    return caught.value.reason


def test_valid_reading():
    reading = parse(payload(dissolved_oxygen=6.1, temperature=29.9))
    assert reading.device == DEVICE
    assert reading.ts == NOW
    assert reading.value("dissolved_oxygen") == 6.1
    assert reading.value("ph") is None


def test_timestamp_is_stored_in_utc():
    body = json.dumps({"ts": "2026-11-08T17:30:00+05:30", "ph": 7.5}).encode()
    assert parse(body).ts == NOW


def test_unknown_numeric_field_becomes_extra_sensor():
    reading = parse(payload(dissolved_oxygen=6.0, turbidity=12.5))
    assert reading.extra == {"turbidity": 12.5}
    assert reading.value("turbidity") == 12.5


def test_non_numeric_extras_are_ignored():
    reading = parse(payload(ph=7.0, firmware="1.2", online=True, BadKey=1))
    assert reading.extra is None


def test_impossible_value_is_dropped_but_other_sensors_are_kept():
    reading = parse(payload(dissolved_oxygen=99, ph=7.1))
    assert reading.value("dissolved_oxygen") is None
    assert reading.value("ph") == 7.1


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"not json", "invalid_payload"),
        (json.dumps({"ph": 7}).encode(), "invalid_payload"),
        (json.dumps({"ts": "2026-11-08T12:00:00", "ph": 7}).encode(), "invalid_payload"),
        (payload(ph="7"), "invalid_payload"),
        (payload(ph=True), "invalid_payload"),
        (payload(dissolved_oxygen=99), "no_valid_values"),
        (payload(), "no_valid_values"),
    ],
)
def test_rejected_payloads(body, reason):
    assert rejected_reason(body) == reason


def test_nan_is_rejected():
    assert rejected_reason(b'{"ts":"2026-11-08T12:00:00Z","ph":NaN}') == "invalid_payload"


def test_future_timestamp_is_rejected():
    future = (NOW + timedelta(minutes=10)).isoformat()
    assert rejected_reason(json.dumps({"ts": future, "ph": 7}).encode()) == "timestamp_in_future"


def test_small_clock_drift_is_accepted():
    ahead = (NOW + timedelta(minutes=2)).isoformat()
    assert parse(json.dumps({"ts": ahead, "ph": 7}).encode()).value("ph") == 7


def test_very_old_timestamp_is_rejected():
    old = (NOW - timedelta(days=31)).isoformat()
    assert rejected_reason(json.dumps({"ts": old, "ph": 7}).encode()) == "timestamp_too_old"


def test_unknown_device_is_rejected():
    assert rejected_reason(payload(ph=7), "aqua/devices/OTHER/telemetry") == "unknown_device"


@pytest.mark.parametrize("topic", ["aqua/devices/SN1", "x/devices/SN1/telemetry", "a/b/c/d/e"])
def test_bad_topic_is_rejected(topic):
    assert rejected_reason(payload(ph=7), topic) == "bad_topic"
