"""Telemetry ingest: validate, buffer, save in batches, then check alerts."""
import asyncio
import logging
import time
from collections import Counter, deque
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import METRIC_COLUMNS
from app.repositories.alert import AlertRuleRepository, MetricDefinitionRepository
from app.repositories.device import DeviceLookupRepository
from app.repositories.settings import SettingsRepository
from app.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import TelemetryPayload
from app.services.alerts import AlertService
from app.services.domain import DeviceRef, Reading, ReferenceData
from app.services.pond_status import PondStatusService

logger = logging.getLogger(__name__)


class RejectedReading(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _serial_from_topic(topic: str) -> str:
    parts = topic.split("/")
    if len(parts) != 4 or parts[:2] != ["aqua", "devices"] or parts[3] != "telemetry":
        raise RejectedReading("bad_topic")
    return parts[2]


def _within_limits(
    value: float | None, limits: tuple[float | None, float | None] | None
) -> bool:
    if value is None or limits is None:
        return True
    low, high = limits
    return (low is None or value >= low) and (high is None or value <= high)


def parse_reading(
    topic: str,
    payload: bytes,
    reference: ReferenceData,
    settings: Settings,
    now: datetime,
) -> Reading:
    """Build a Reading from one MQTT message, or raise RejectedReading.

    The device identity comes from the topic, which the broker restricts per
    device login. An impossible value is dropped alone, so one broken sensor
    does not lose the others or raise a false alert.
    """
    device = reference.devices.get(_serial_from_topic(topic))
    if device is None:
        raise RejectedReading("unknown_device")

    try:
        parsed = TelemetryPayload.model_validate_json(payload)
    except ValidationError as exc:
        raise RejectedReading("invalid_payload") from exc

    if parsed.ts > now + timedelta(seconds=settings.max_future_skew_seconds):
        raise RejectedReading("timestamp_in_future")
    if parsed.ts < now - timedelta(days=settings.max_reading_age_days):
        raise RejectedReading("timestamp_too_old")

    limits = reference.metric_limits
    values: dict[str, float | None] = {}
    for metric in METRIC_COLUMNS:
        value = getattr(parsed, metric)
        values[metric] = value if _within_limits(value, limits.get(metric)) else None
    extra = {
        key: value
        for key, value in parsed.extra_metrics().items()
        if _within_limits(value, limits.get(key))
    }
    if not extra and all(value is None for value in values.values()):
        raise RejectedReading("no_valid_values")

    return Reading(
        device=device,
        ts=parsed.ts.astimezone(UTC),
        received_at=now,
        values=values,
        extra=extra or None,
    )


async def load_reference(session: AsyncSession) -> ReferenceData:
    active_devices = await DeviceLookupRepository(session).list_active_devices()
    devices = {
        serial: DeviceRef(device_id, org_id, pond_id, farm_id)
        for serial, device_id, org_id, pond_id, farm_id in active_devices
    }
    rules = await AlertRuleRepository(session).list_all_by_org()
    limits = await MetricDefinitionRepository(session).list_limits()
    settings = await SettingsRepository(session).load_settings()
    return ReferenceData(
        devices=devices,
        rules_by_org=rules,
        metric_limits=limits,
        settings=settings,
    )


class IngestService:
    """Holds readings in memory briefly and saves them in batches."""

    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._buffer: deque[Reading] = deque()
        self._wake = asyncio.Event()
        self.reference = ReferenceData()
        self._reference_loaded_at = 0.0
        self.stats: Counter[str] = Counter()

    async def refresh_reference(self) -> None:
        async with self._session_factory() as session:
            self.reference = await load_reference(session)
        self._reference_loaded_at = time.monotonic()

    def handle_message(self, topic: str, payload: bytes) -> None:
        try:
            reading = parse_reading(
                topic, payload, self.reference, self._settings, datetime.now(UTC)
            )
        except RejectedReading as rejected:
            self.stats[f"rejected_{rejected.reason}"] += 1
            return

        if len(self._buffer) >= self._settings.ingest_max_buffer:
            # Database is down for too long. Newest data matters most.
            self._buffer.popleft()
            self.stats["dropped_buffer_full"] += 1
        self._buffer.append(reading)
        self.stats["received"] += 1
        if len(self._buffer) >= self.reference.settings.get("ingest_batch_size", 500):
            self._wake.set()

    async def flush(self) -> int:
        """Save one batch. On a database outage the batch stays in the buffer."""
        size = self.reference.settings.get("ingest_batch_size", 500)
        # Taken out while saving, so a full buffer cannot drop rows mid-save.
        batch = [self._buffer.popleft() for _ in range(min(size, len(self._buffer)))]
        if not batch:
            return 0
        try:
            try:
                await self._persist(batch)
            except (DataError, IntegrityError):
                # Retrying the same bad row forever would block all ingest.
                logger.exception("Batch rejected by database, saving rows one at a time")
                await self._persist_individually(batch)
        except BaseException:
            self._buffer.extendleft(reversed(batch))
            raise
        return len(batch)

    async def _persist_individually(self, batch: Sequence[Reading]) -> None:
        for reading in batch:
            try:
                await self._persist([reading])
            except (DataError, IntegrityError):
                logger.exception("Dropping reading from device %s", reading.device.id)
                self.stats["dropped_database_rejected"] += 1

    async def _persist(self, batch: Sequence[Reading]) -> None:
        now = datetime.now(UTC)
        # A broker may redeliver a message, so one reading can appear twice.
        unique = {(r.device.id, r.ts): r for r in batch}
        ordered = sorted(unique.values(), key=lambda r: r.ts)

        async with self._session_factory() as session:
            repository = TelemetryRepository(session)
            await repository.insert_readings([r.as_row() for r in ordered])

            device_ids = sorted({r.device.id for r in ordered})
            previous = await repository.latest_timestamps(device_ids)
            # Delayed readings are stored but must not raise old alerts.
            new = [
                r for r in ordered
                if r.device.id not in previous or r.ts > previous[r.device.id]
            ]
            if new:
                newest = {r.device.id: r for r in new}
                # Fixed order, so two workers cannot deadlock on the same rows.
                await repository.upsert_latest(
                    [newest[device_id].as_row() for device_id in sorted(newest)]
                )
                await AlertService(session).process(new, self.reference, now)
                pond_ids = {r.device.pond_id for r in new if r.device.pond_id}
                if pond_ids:
                    await PondStatusService(session).recompute(
                        now, self.reference.settings.get("offline_timeout_minutes", 5), pond_ids
                    )
            await session.commit()
        self.stats["saved"] += len(ordered)

    async def run(self) -> None:
        """Save buffered readings until cancelled."""
        backoff = 1.0
        last_report = time.monotonic()
        while True:
            flush_seconds = self.reference.settings.get("ingest_flush_seconds", 1)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=flush_seconds)
            except TimeoutError:
                pass
            self._wake.clear()

            try:
                elapsed = time.monotonic() - self._reference_loaded_at
                if elapsed >= self._settings.reference_refresh_seconds:
                    await self.refresh_reference()
                while await self.flush():
                    pass
                backoff = 1.0
            except Exception:
                logger.exception(
                    "Saving failed, retrying in %.0fs (%d readings waiting)",
                    backoff,
                    len(self._buffer),
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

            if time.monotonic() - last_report >= 60:
                logger.info("Ingest stats: %s, buffered=%d", dict(self.stats), len(self._buffer))
                self.stats.clear()
                last_report = time.monotonic()

    async def drain(self) -> None:
        """Best effort save during shutdown."""
        try:
            while await self.flush():
                pass
        except Exception:
            logger.exception("Could not save %d readings at shutdown", len(self._buffer))
