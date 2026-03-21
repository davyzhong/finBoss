"""飞书 Webhook 端点"""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from services.feishu.event_handler import EventHandler

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/events")
async def handle_feishu_event(request: Request) -> JSONResponse:
    """
    飞书事件 Webhook 端点

    支持:
    - URL 注册验证 (challenge)
    - 消息事件 (im.message.receive_v1)
    - 卡片按钮回调
    """
    body = await request.body()
    handler = EventHandler()

    # 验证签名（如已配置）
    signature = request.headers.get("X-Lark-Signature", "")
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    if signature and not handler.feishu_client.verify_signature(signature, timestamp, body):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(body)

    # URL 注册验证
    if "challenge" in payload:
        return JSONResponse(content={"challenge": payload["challenge"]})

    # 事件处理
    event = payload.get("event", {})
    event_type = payload.get("header", {}).get("event_type", "")

    if event_type == "im.message.receive_v1":
        await handler.handle_message(event)

    # 飞书要求 3s 内返回 200
    return JSONResponse(content={"code": 0, "msg": "success"})
