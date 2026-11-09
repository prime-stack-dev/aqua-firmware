"""Jobs worker entry point. Run with: python -m app.jobs.worker"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, engine
from app.core.logging import configure_logging
from app.services.maintenance import ensure_partitions, run_health_check, try_job_lock

logger = logging.getLogger(__name__)

Job = Callable[[AsyncSession, datetime], Awaitable[object]]


async def run_forever(name: str, job_id: int, every_seconds: int, job: Job) -> None:
    """Run a job on a timer. A failure is logged and tried again next time."""
    while True:
        try:
            async with SessionFactory() as session:
                if await try_job_lock(session, job_id):
                    await job(session, datetime.now(UTC))
                    await session.commit()
        except Exception:
            logger.exception("Job %s failed", name)
        await asyncio.sleep(every_seconds)


async def main() -> None:
    configure_logging()
    try:
        await asyncio.gather(
            run_forever("health-check", 1001, 60, run_health_check),
            run_forever("partitions", 1002, 86_400, ensure_partitions),
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
