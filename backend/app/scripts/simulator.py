"""Pretend to be many devices, for development and load testing.

Usage: python -m app.scripts.simulator --password <simulator-password> [--devices 1000]

Each device sends at its own random second within the interval, which is how
real firmware should behave.
"""
import argparse
import asyncio
import json
import random
from datetime import UTC, datetime

import aiomqtt

from app.core.config import get_settings


def build_payload(rng: random.Random) -> str:
    return json.dumps(
        {
            "ts": datetime.now(UTC).isoformat(),
            "dissolved_oxygen": round(rng.uniform(3.5, 7.5), 2),
            "temperature": round(rng.uniform(27.0, 32.0), 2),
            "ph": round(rng.uniform(7.2, 8.4), 2),
            "salinity": round(rng.uniform(10.0, 20.0), 2),
            "ammonia": round(rng.uniform(0.0, 0.3), 3),
        }
    )


async def simulate_device(
    client: aiomqtt.Client, serial: str, interval: float, rng: random.Random
) -> None:
    await asyncio.sleep(rng.uniform(0, interval))
    while True:
        await client.publish(f"aqua/devices/{serial}/telemetry", build_payload(rng), qos=1)
        await asyncio.sleep(interval)


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    rng = random.Random()
    async with aiomqtt.Client(
        hostname=settings.mqtt_broker_host,
        port=settings.mqtt_broker_port,
        username=args.username,
        password=args.password,
        identifier="aqua-simulator",
        max_inflight_messages=1000,
    ) as client:
        print(f"Simulating {args.devices} devices every {args.interval:g}s. Ctrl+C to stop.")
        async with asyncio.TaskGroup() as group:
            for number in range(1, args.devices + 1):
                group.create_task(
                    simulate_device(client, f"SIM-{number:05d}", args.interval, rng)
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", type=int, default=20)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--username", default="simulator")
    parser.add_argument("--password", required=True)
    try:
        asyncio.run(run(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
