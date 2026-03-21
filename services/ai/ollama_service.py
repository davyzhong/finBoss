"""Ollama 本地 LLM 服务（支持同步和异步调用）"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx

from api.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class OllamaService:
    """Ollama 本地 LLM 推理服务封装（同步 + 异步）"""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        http_client: type[httpx.AsyncClient] | None = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.ollama.base_url
        self.model = model or settings.ollama.model
        self.temperature = settings.ollama.temperature
        self.max_tokens = settings.ollama.max_tokens
        self.timeout = timeout or settings.ollama.timeout
        # 允许注入自定义 AsyncClient（用于测试）
        self._http_client_cls: type[httpx.AsyncClient] = http_client or httpx.AsyncClient

    # ------------------------------------------------------------------
    # 同步方法（向后兼容）
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """生成文本（同步）"""
        return asyncio.get_event_loop().run_until_complete(
            self.agenerate(prompt, system, temperature, max_tokens)
        )

    def generate_raw(
        self,
        prompt: str,
        system: str | None = None,
    ) -> dict[str, Any]:
        """生成文本（返回完整响应，同步）"""
        return asyncio.get_event_loop().run_until_complete(
            self.agenerate_raw(prompt, system)
        )

    def is_available(self) -> bool:
        """检查 Ollama 服务是否可用（同步）"""
        return asyncio.get_event_loop().run_until_complete(self.ais_available())

    def list_models(self) -> list[dict[str, Any]]:
        """列出可用的模型（同步）"""
        return asyncio.get_event_loop().run_until_complete(self.alist_models())

    # ------------------------------------------------------------------
    # 异步方法（推荐在 async 上下文中使用，不阻塞事件循环）
    # ------------------------------------------------------------------

    async def _make_request(self, path: str, **kwargs) -> httpx.Response:
        """发送 HTTP 请求的异步方法（可注入 mock）"""
        async with self._http_client_cls(timeout=self.timeout) as client:
            return await client.post(f"{self.base_url}{path}", **kwargs)

    async def agenerate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """生成文本（异步，非阻塞）"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": False,
        }
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        async with self._http_client_cls(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = await response.json()
            return data["message"]["content"]

    async def agenerate_raw(
        self,
        prompt: str,
        system: str | None = None,
    ) -> dict[str, Any]:
        """生成文本（返回完整响应，异步）"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }

        async with self._http_client_cls(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return await response.json()

    async def ais_available(self) -> bool:
        """检查 Ollama 服务是否可用（异步）"""
        try:
            async with self._http_client_cls(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def alist_models(self) -> list[dict[str, Any]]:
        """列出可用的模型（异步）"""
        try:
            async with self._http_client_cls(timeout=10) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = await response.json()
                return data.get("models", [])
        except Exception:
            return []
