from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting
from app.repositories.base import BaseRepository

DEFAULTS = {
    "offline_timeout_minutes": 5,
    "ingest_batch_size": 500,
    "ingest_flush_seconds": 1,
}


class SettingsRepository(BaseRepository[SystemSetting]):
    """System-level runtime configuration repository."""

    model = SystemSetting

    async def load_settings(self) -> dict[str, int]:
        """Runtime settings. A missing or invalid row falls back to its default."""
        rows = (await self.session.execute(select(SystemSetting.key, SystemSetting.value))).all()
        stored = dict(rows)
        result = {}
        for key, default in DEFAULTS.items():
            value = stored.get(key, default)
            valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
            result[key] = value if valid else default
        return result


async def load_settings(session: AsyncSession) -> dict[str, int]:
    """Runtime settings helper for callers with only an AsyncSession."""
    return await SettingsRepository(session).load_settings()
