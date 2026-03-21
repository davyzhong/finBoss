# connectors/kingdee/client.py
"""金蝶星空 Cloud API 客户端"""
from typing import Any

import httpx


class KingdeeClient:
    """金蝶 API REST 客户端"""

    def __init__(
        self,
        base_url: str,
        app_id: str,
        app_secret: str,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self._token: str | None = None

    def _get_token(self) -> str:
        """获取访问令牌"""
        if self._token:
            return self._token
        url = f"{self.base_url}/api/v2/auth/token"
        payload = {"appId": self.app_id, "appSecret": self.app_secret}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            return self._token

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """GET 请求"""
        url = f"{self.base_url}/api/v2{endpoint}"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json().get("data", [])

    def get_ar_verify_list(
        self,
        org_id: str,
        start_date: str,
        end_date: str,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """获取应收单列表"""
        return self.get(
            "/ar/verify",
            params={
                "orgId": org_id,
                "startDate": start_date,
                "endDate": end_date,
                "page": page,
                "pageSize": page_size,
            },
        )
