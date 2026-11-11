"""Initial schema and default configuration.

Revision ID: 0001
Revises:
"""
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_now = sa.text("now()")
_ts = sa.DateTime(timezone=True)
_jsonb = postgresql.JSONB(none_as_null=True)


def _reading_columns() -> list[sa.Column]:
    return [
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("pond_id", sa.Uuid(), nullable=True),
        sa.Column("dissolved_oxygen", sa.Double(), nullable=True),
        sa.Column("temperature", sa.Double(), nullable=True),
        sa.Column("ph", sa.Double(), nullable=True),
        sa.Column("salinity", sa.Double(), nullable=True),
        sa.Column("ammonia", sa.Double(), nullable=True),
        sa.Column("extra", _jsonb, nullable=True),
        sa.Column("received_at", _ts, server_default=_now, nullable=False),
    ]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, (total % 12) + 1


def _monthly_partitions(past_months: int = 6, future_months: int = 6) -> list[str]:
    today = datetime.now(UTC)
    start_year, start_month = _shift_month(today.year, today.month, -past_months)
    total_months = past_months + 1 + future_months
    statements = []
    year, month = start_year, start_month
    for _ in range(total_months):
        next_year, next_month = _shift_month(year, month, 1)
        statements.append(
            f"CREATE TABLE IF NOT EXISTS telemetry_y{year}m{month:02d} PARTITION OF telemetry "
            f"FOR VALUES FROM ('{year}-{month:02d}-01+00') "
            f"TO ('{next_year}-{next_month:02d}-01+00')"
        )
        year, month = next_year, next_month
    return statements


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'TimescaleDB extension not available or skipped.';
        END
        $$;
        """
    )
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_memberships_org_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "org_id", name="pk_memberships"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", _ts, nullable=False),
        sa.Column("revoked_at", _ts, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_refresh_tokens_org_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_table(
        "farms",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_farms_org_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_farms"),
        sa.UniqueConstraint("org_id", "name", name="uq_farms_org_id_name"),
    )
    op.create_index("ix_farms_org_id", "farms", ["org_id"])
    op.create_table(
        "ponds",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("farm_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), server_default="UNKNOWN", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["farm_id"], ["farms.id"], name="fk_ponds_farm_id_farms", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_ponds_org_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ponds"),
        sa.UniqueConstraint("farm_id", "name", name="uq_ponds_farm_id_name"),
    )
    op.create_index("ix_ponds_org_id", "ponds", ["org_id"])
    op.create_table(
        "devices",
        sa.Column("serial", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("pond_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_devices_org_id_organizations", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pond_id"], ["ponds.id"], name="fk_devices_pond_id_ponds", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("serial", name="uq_devices_serial"),
    )
    op.create_index("ix_devices_org_id", "devices", ["org_id"])
    op.create_index("ix_devices_pond_id", "devices", ["pond_id"])
    op.create_table(
        "plans",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=True),
        sa.Column("grace_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("raw_retention_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column("hourly_retention_days", sa.Integer(), server_default="730", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
        sa.UniqueConstraint("name", name="uq_plans_name"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("starts_at", _ts, nullable=False),
        sa.Column("ends_at", _ts, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"],
            name="fk_subscriptions_device_id_devices", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_subscriptions_org_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name="fk_subscriptions_plan_id_plans", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])
    op.create_index("ix_subscriptions_device_id_ends_at", "subscriptions", ["device_id", "ends_at"])

    op.create_table(
        "telemetry",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("ts", _ts, nullable=False),
        *_reading_columns(),
        sa.PrimaryKeyConstraint("device_id", "ts", name="pk_telemetry"),
        postgresql_partition_by="RANGE (ts)",
    )
    for statement in _monthly_partitions(past_months=6, future_months=6):
        op.execute(statement)

    op.create_table(
        "device_latest",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("ts", _ts, nullable=False),
        *_reading_columns(),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"],
            name="fk_device_latest_device_id_devices", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", name="pk_device_latest"),
    )
    op.create_index("ix_device_latest_org_id", "device_latest", ["org_id"])
    op.create_index("ix_device_latest_pond_id", "device_latest", ["pond_id"])

    metrics = op.create_table(
        "metric_definitions",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("min_valid", sa.Double(), nullable=True),
        sa.Column("max_valid", sa.Double(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_metric_definitions"),
    )
    rules = op.create_table(
        "alert_rules",
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("farm_id", sa.Uuid(), nullable=True),
        sa.Column("pond_id", sa.Uuid(), nullable=True),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Double(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("clear_after", sa.Integer(), server_default="3", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _ts, server_default=_now, nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(farm_id, pond_id) <= 1", name="ck_alert_rules_one_scope"
        ),
        sa.ForeignKeyConstraint(
            ["farm_id"], ["farms.id"], name="fk_alert_rules_farm_id_farms", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["metric"], ["metric_definitions.key"],
            name="fk_alert_rules_metric_metric_definitions",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_alert_rules_org_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pond_id"], ["ponds.id"], name="fk_alert_rules_pond_id_ponds", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_alert_rules"),
        sa.UniqueConstraint(
            "org_id", "farm_id", "pond_id", "metric", "severity",
            name="uq_alert_rules_org_id_farm_id_pond_id_metric_severity",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_alert_rules_org_id", "alert_rules", ["org_id"])
    op.create_table(
        "alerts",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("pond_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), server_default="open", nullable=False),
        sa.Column("threshold", sa.Double(), nullable=True),
        sa.Column("last_value", sa.Double(), nullable=True),
        sa.Column("ok_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("opened_at", _ts, nullable=False),
        sa.Column("acknowledged_at", _ts, nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("closed_at", _ts, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["users.id"],
            name="fk_alerts_acknowledged_by_users", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_alerts_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_alerts_org_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pond_id"], ["ponds.id"], name="fk_alerts_pond_id_ponds", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["alert_rules.id"], name="fk_alerts_rule_id_alert_rules", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
    )
    op.create_index(
        "ix_alerts_org_id_state_opened_at", "alerts", ["org_id", "state", sa.text("opened_at DESC")]
    )
    op.create_index(
        "uq_alerts_live_threshold", "alerts", ["device_id", "metric"], unique=True,
        postgresql_where=sa.text("kind = 'threshold' AND state <> 'closed'"),
    )
    op.create_index(
        "uq_alerts_live_no_data", "alerts", ["device_id"], unique=True,
        postgresql_where=sa.text("kind = 'no_data' AND state <> 'closed'"),
    )
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_system_settings"),
    )

    op.bulk_insert(
        metrics,
        [
            {"key": "dissolved_oxygen", "label": "Dissolved oxygen", "unit": "mg/L",
             "min_valid": 0, "max_valid": 25},
            {"key": "temperature", "label": "Temperature", "unit": "°C",
             "min_valid": -5, "max_valid": 60},
            {"key": "ph", "label": "pH", "unit": None, "min_valid": 0, "max_valid": 14},
            {"key": "salinity", "label": "Salinity", "unit": "ppt",
             "min_valid": 0, "max_valid": 80},
            {"key": "ammonia", "label": "Ammonia", "unit": "mg/L",
             "min_valid": 0, "max_valid": 100},
        ],
    )
    op.bulk_insert(
        rules,
        [
            {"id": uuid.uuid4(), "metric": "dissolved_oxygen", "operator": "lt",
             "threshold": 4.0, "severity": "critical"},
            {"id": uuid.uuid4(), "metric": "dissolved_oxygen", "operator": "lt",
             "threshold": 5.0, "severity": "low"},
        ],
    )
    op.execute(
        "INSERT INTO system_settings (key, value) VALUES "
        "('offline_timeout_minutes', '5'::jsonb), "
        "('ingest_batch_size', '500'::jsonb), "
        "('ingest_flush_seconds', '1'::jsonb)"
    )


def downgrade() -> None:
    for table in (
        "system_settings", "alerts", "alert_rules", "metric_definitions", "device_latest",
        "telemetry", "subscriptions", "plans", "devices", "ponds", "farms",
        "refresh_tokens", "memberships", "users", "organizations",
    ):
        op.drop_table(table)
