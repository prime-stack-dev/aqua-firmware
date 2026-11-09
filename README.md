# Aqua OS backend

Devices publish readings over MQTT once a minute. A worker validates and saves
them to PostgreSQL, and customers read them through a FastAPI API.

```
Devices -> Mosquitto -> Ingest worker -> PostgreSQL <- Jobs worker
                                             ^
                                          FastAPI
```

| Process | Command | Job |
|---|---|---|
| API | `uvicorn app.main:app` | Customer REST API, docs at `/docs` |
| Ingest | `python -m app.mqtt.worker` | Validates and saves readings, checks alerts |
| Jobs | `python -m app.jobs.worker` | Offline detection, pond status, monthly partitions |

## Run locally

```bash
cp backend/.env.example backend/.env         # then replace every change-me value
docker compose up --build
docker compose exec api python -m app.scripts.seed_demo --password <choose-one>
docker compose exec api python -m app.scripts.simulator --password <MQTT_SIMULATOR_PASSWORD>
```

Log in at `http://localhost:8000/docs` as `owner@example.com`.

## Environment files

| File | Used by | Contains |
|---|---|---|
| `backend/.env` | API, workers, PostgreSQL, Mosquitto | Secrets and server settings |

This file is not committed to git.

## Run tests

```bash
cd backend && pip install -r requirements-dev.txt && cd ..
docker compose up -d postgres-db
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<test-db> pytest
```

Tests marked `db` skip when PostgreSQL is not reachable. They delete data, so
always point `DATABASE_URL` at a separate test database.

## Device message

Topic: `aqua/devices/{serial}/telemetry` with QoS 1.

```json
{"ts": "2026-11-08T12:00:00Z", "dissolved_oxygen": 6.1, "temperature": 29.9, "ph": 7.8, "salinity": 15.2, "ammonia": 0.02}
```

- `ts` must include a timezone.
- Any other numeric field is stored as an extra sensor, with no database change.
- Firmware should send at a random second within the minute and keep unsent
  readings while offline.

## Where things live

| Folder | Contents |
|---|---|
| `backend/app/api/v1` | HTTP routes |
| `backend/app/services` | Business rules |
| `backend/app/repositories` | Database queries. `TenantRepository` separates customers |
| `backend/app/models` | Tables |
| `backend/app/schemas` | Request, response and device message formats |
| `backend/app/mqtt` | Broker connection and ingest worker |
| `backend/app/jobs` | Scheduled background work |
| `backend/alembic` | Database migrations |
