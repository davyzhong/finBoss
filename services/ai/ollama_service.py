"""Ollama 本地 LLM 服务"""

from typing import Any

import httpx

from api.config import get_settings


class OllamaService:
    """Ollama 本地 LLM 推理服务封装"""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.ollama.base_url
        self.model = model or settings.ollama.model
        self.temperature = settings.ollama.temperature
        self.max_tokens = settings.ollama.max_tokens
        self.timeout = timeout or settings.ollama.timeout

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """生成文本

        Args:
            prompt: 用户提示词
            system: 系统提示词
            temperature: 生成温度
            max_tokens: 最大token数

        Returns:
            生成的文本
        """
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

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    def generate_raw(
        self,
        prompt: str,
        system: str | None = None,
    ) -> dict[str, Any]:
        """生成文本（返回完整响应）

        Args:
            prompt: 用户提示词
            system: 系统提示词

        Returns:
            完整的 API 响应
        """
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

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def is_available(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        """列出可用的模型"""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return data.get("models", [])
        except Exception:
            return []
