"""Create demo data for local development. Safe to run twice.

Usage: python -m app.scripts.seed_demo --password <choose-one> [--devices 20]

Devices are named SIM-00001, SIM-00002, and so on, one per pond, to match
the simulator.
"""
import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.core.security import hash_password
from app.models import Device, Farm, Membership, Organization, Plan, Pond, Subscription, User
from app.models.enums import Role

PONDS_PER_FARM = 20


async def seed(password: str, device_count: int) -> None:
    async with SessionFactory() as session:
        exists = await session.scalar(
            select(Organization).where(Organization.slug == "farm-alpha")
        )
        if exists:
            print("Demo data already exists.")
            return

        org = Organization(name="Farm Alpha", slug="farm-alpha")
        plan = Plan(name="Standard")
        owner = User(
            email="owner@example.com",
            full_name="Demo Owner",
            password_hash=hash_password(password),
        )
        session.add_all([org, plan, owner])
        session.add(
            User(
                email="admin@example.com",
                full_name="Platform Admin",
                password_hash=hash_password(password),
                is_platform_admin=True,
            )
        )
        await session.flush()
        session.add(Membership(user_id=owner.id, org_id=org.id, role=Role.OWNER))

        now = datetime.now(UTC)
        farm = None
        for number in range(1, device_count + 1):
            if (number - 1) % PONDS_PER_FARM == 0:
                farm_number = (number - 1) // PONDS_PER_FARM + 1
                farm = Farm(org_id=org.id, name=f"Farm {farm_number:03d}")
                session.add(farm)
                await session.flush()
            pond = Pond(org_id=org.id, farm_id=farm.id, name=f"Pond {number:05d}")
            session.add(pond)
            await session.flush()
            device = Device(serial=f"SIM-{number:05d}", org_id=org.id, pond_id=pond.id)
            session.add(device)
            await session.flush()
            session.add(
                Subscription(
                    org_id=org.id,
                    device_id=device.id,
                    plan_id=plan.id,
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=365),
                )
            )
        await session.commit()
        print(f"Created owner@example.com, admin@example.com and {device_count} devices.")
    await engine.dispose()


def main() -> None:
    if get_settings().environment == "production":
        raise SystemExit("Refusing to create demo data in production.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", required=True)
    parser.add_argument("--devices", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(seed(args.password, args.devices))


if __name__ == "__main__":
    main()
