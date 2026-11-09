"""Infrastructure settings, loaded from environment variables.

Business settings an admin can change at runtime live in the
`system_settings` table instead. See app/repositories/settings.py.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    cors_origins: list[str] = []

    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    mqtt_telemetry_topic: str = "aqua/devices/+/telemetry"
    # Workers in the same group share the load. Empty disables sharing.
    mqtt_shared_group: str = "ingest"

    ingest_max_buffer: int = 100_000
    reference_refresh_seconds: int = 60
    max_future_skew_seconds: int = 300
    max_reading_age_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
