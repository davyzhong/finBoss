"""预警规则 API 路由"""
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated

from services.alert_service import AlertService
from api.schemas.alert import AlertRuleCreate, AlertRuleResponse, AlertHistoryResponse
from api.dependencies import AlertServiceDep

router = APIRouter(tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(service: AlertServiceDep):
    """列出所有预警规则"""
    rows = service.list_rules()
    return rows


@router.post("/rules", response_model=dict)
async def create_rule(data: AlertRuleCreate, service: AlertServiceDep):
    """创建预警规则"""
    rule_id = service.create_rule(data.model_dump())
    return {"id": rule_id, "status": "created"}


@router.put("/rules/{rule_id}", response_model=dict)
async def update_rule(rule_id: str, data: AlertRuleCreate, service: AlertServiceDep):
    """更新预警规则"""
    service.update_rule(rule_id, data.model_dump())
    return {"id": rule_id, "status": "updated"}


@router.delete("/rules/{rule_id}", response_model=dict)
async def delete_rule(rule_id: str, service: AlertServiceDep):
    """删除预警规则"""
    service.delete_rule(rule_id)
    return {"id": rule_id, "status": "deleted"}


@router.get("/history", response_model=list[AlertHistoryResponse])
async def get_history(service: AlertServiceDep, limit: int = 100):
    """查询预警触发历史"""
    return service.get_history(limit=limit)


@router.post("/trigger", response_model=dict)
async def trigger_alerts(service: AlertServiceDep):
    """手动触发一次预警评估"""
    alerts = service.evaluate_all()
    return {"triggered": len(alerts), "alerts": [
        {"rule_id": a.rule_id, "rule_name": a.rule_name, "level": a.alert_level}
        for a in alerts
    ]}
