import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError

from app.api.v1.deps import (
    Limit,
    Member,
    Offset,
    SessionDep,
    require_roles,
    tenant_repo,
    utc_now,
)
from app.core.errors import AppError, not_found
from app.models import AlertRule
from app.models.enums import AlertState, Role
from app.repositories.alert import TenantAlertRepository, TenantAlertRuleRepository
from app.repositories.farm import FarmRepository, PondRepository
from app.schemas.resources import AlertOut, AlertRuleCreate, AlertRuleOut, AlertRuleUpdate

router = APIRouter(tags=["alerts"])

Alerts = Annotated[TenantAlertRepository, tenant_repo(TenantAlertRepository)]
Rules = Annotated[TenantAlertRuleRepository, tenant_repo(TenantAlertRuleRepository)]
CanOperate = Annotated[Member, Depends(require_roles(Role.OWNER, Role.MANAGER))]
OwnerOnly = Depends(require_roles(Role.OWNER))


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    alerts: Alerts, state: AlertState | None = None, limit: Limit = 100, offset: Offset = 0
):
    return await alerts.list_visible(utc_now(), state, limit, offset)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: uuid.UUID, alerts: Alerts, member: CanOperate, session: SessionDep
):
    now = utc_now()
    alert = await alerts.get_visible(alert_id, now)
    if alert is None:
        raise not_found("Alert")
    if alert.state == AlertState.CLOSED:
        raise AppError(409, "Alert is already closed")
    alert.state = AlertState.ACKNOWLEDGED
    alert.acknowledged_at = now
    alert.acknowledged_by = member.user_id
    await session.commit()
    return alert


@router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_rules(rules: Rules):
    return await rules.list_with_defaults()


@router.post(
    "/alert-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[OwnerOnly],
)
async def create_rule(body: AlertRuleCreate, rules: Rules, session: SessionDep):
    if not await rules.metric_exists(body.metric):
        raise AppError(422, "Unknown metric")
    if body.farm_id and not await FarmRepository(session, rules.org_id).get(body.farm_id):
        raise not_found("Farm")
    if body.pond_id and not await PondRepository(session, rules.org_id).get(body.pond_id):
        raise not_found("Pond")

    rule = rules.add(AlertRule(org_id=rules.org_id, **body.model_dump()))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(409, "A rule for this scope and severity already exists") from exc
    return rule


@router.put("/alert-rules/{rule_id}", response_model=AlertRuleOut, dependencies=[OwnerOnly])
async def update_rule(
    rule_id: uuid.UUID, body: AlertRuleUpdate, rules: Rules, session: SessionDep
):
    rule = await rules.get(rule_id)
    if rule is None:
        raise not_found("Alert rule")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(409, "A rule for this scope and severity already exists") from exc
    return rule


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[OwnerOnly],
)
async def delete_rule(rule_id: uuid.UUID, rules: Rules, session: SessionDep) -> None:
    rule = await rules.get(rule_id)
    if rule is None:
        raise not_found("Alert rule")
    await rules.delete(rule)
    await session.commit()
