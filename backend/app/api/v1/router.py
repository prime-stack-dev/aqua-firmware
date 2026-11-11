from fastapi import APIRouter

from app.api.v1 import admin, alerts, auth, farms, members, subscriptions, telemetry

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(members.router)
api_router.include_router(farms.router)
api_router.include_router(telemetry.router)
api_router.include_router(alerts.router)
api_router.include_router(subscriptions.router)
api_router.include_router(admin.router)
