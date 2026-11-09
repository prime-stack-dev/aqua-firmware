from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting

DEFAULTS = {
    "offline_timeout_minutes": 5,
    "ingest_batch_size": 500,
    "ingest_flush_seconds": 1,
}


async def load_settings(session: AsyncSession) -> dict[str, int]:
    """Runtime settings. A missing or invalid row falls back to its default."""
    rows = (await session.execute(select(SystemSetting.key, SystemSetting.value))).all()
    stored = dict(rows)
    result = {}
    for key, default in DEFAULTS.items():
        value = stored.get(key, default)
        valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
        result[key] = value if valid else default
    return result
