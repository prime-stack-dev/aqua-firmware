"""Ingest worker entry point. Run with: python -m app.mqtt.worker"""
import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.core.logging import configure_logging
from app.mqtt.subscriber import TelemetrySubscriber
from app.services.ingest import IngestService

logger = logging.getLogger(__name__)


async def _load_reference_with_retry(service: IngestService) -> None:
    while True:
        try:
            await service.refresh_reference()
            return
        except Exception:
            logger.exception("Database not ready, retrying in 5s")
            await asyncio.sleep(5)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    service = IngestService(SessionFactory, settings)
    await _load_reference_with_retry(service)
    subscriber = TelemetrySubscriber(settings, service.handle_message)

    tasks = [
        asyncio.create_task(subscriber.run(), name="mqtt"),
        asyncio.create_task(service.run(), name="flush"),
    ]
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [task.cancel() for task in tasks])

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutting down")
    finally:
        await service.drain()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
