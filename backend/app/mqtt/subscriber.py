import asyncio
import logging
import socket
from collections.abc import Callable

import aiomqtt

from app.core.config import Settings

logger = logging.getLogger(__name__)

_MAX_RECONNECT_SECONDS = 30.0


class TelemetrySubscriber:
    """Owns the broker connection and reconnects whenever it drops."""

    def __init__(self, settings: Settings, on_message: Callable[[str, bytes], None]) -> None:
        self._settings = settings
        self._on_message = on_message

    @property
    def topic(self) -> str:
        telemetry = self._settings.mqtt_telemetry_topic
        group = self._settings.mqtt_shared_group
        return f"$share/{group}/{telemetry}" if group else telemetry

    def _client(self) -> aiomqtt.Client:
        settings = self._settings
        return aiomqtt.Client(
            hostname=settings.mqtt_broker_host,
            port=settings.mqtt_broker_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            # A stable identity lets the broker hold messages during a restart.
            identifier=f"aqua-ingest-{socket.gethostname()}",
            clean_session=False,
            tls_params=aiomqtt.TLSParameters() if settings.mqtt_tls else None,
        )

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                async with self._client() as client:
                    await client.subscribe(self.topic, qos=1)
                    logger.info("Subscribed to %s", self.topic)
                    delay = 1.0
                    async for message in client.messages:
                        self._on_message(message.topic.value, bytes(message.payload))
            except aiomqtt.MqttError as exc:
                logger.warning("MQTT connection lost (%s), retrying in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_SECONDS)
