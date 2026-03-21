"""飞书 SDK 封装"""
import hashlib
import hmac
import time
from typing import Any

import httpx

from services.feishu.config import get_feishu_config


class FeishuClient:
    """飞书 SDK 封装"""

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        config = get_feishu_config()
        self.app_id = app_id or config.app_id
        self.app_secret = app_secret or config.app_secret
        self.bot_name = config.bot_name
        self._tenant_access_token: str | None = None
        self._token_expires_at: float = 0

    def _get_tenant_token(self) -> str:
        """获取 tenant access token（自动缓存）"""
        if self._tenant_access_token and time.time() < self._token_expires_at - 60:
            return self._tenant_access_token

        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
        data = response.json()
        self._tenant_access_token = data.get("tenant_access_token", "")
        self._token_expires_at = time.time() + data.get("expire", 7200)
        return self._tenant_access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json",
        }

    def send_message(self, receive_id: str, msg_type: str, content: dict) -> bool:
        """发送消息"""
        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                headers=self._headers(),
                json={
                    "receive_id": receive_id,
                    "msg_type": msg_type,
                    "content": content,
                },
            )
        return response.status_code == 200

    def send_card(self, receive_id: str, card_content: dict) -> bool:
        """发送卡片消息"""
        card_json = {"config": {"wide_screen_mode": True}, "elements": card_content.get("elements", [])}
        return self.send_message(receive_id=receive_id, msg_type="interactive", content={"zh_cn": card_json})

    def reply_message(self, message_id: str, msg_type: str, content: dict) -> bool:
        """回复消息"""
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                headers=self._headers(),
                json={"msg_type": msg_type, "content": content},
            )
        return response.status_code == 200

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取用户信息"""
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}",
                headers=self._headers(),
            )
        if response.status_code == 200:
            return response.json().get("data", {}).get("user", {})
        return {}

    def verify_signature(self, signature: str, timestamp: str, raw_body: bytes) -> bool:
        """验证飞书事件签名"""
        if not signature:
            return False
        secret = get_feishu_config().verification_token
        if not secret:
            return True  # 未配置 token 时跳过验证
        string_to_sign = f"{timestamp}{raw_body.decode()}"
        sign = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
        return sign == signature
