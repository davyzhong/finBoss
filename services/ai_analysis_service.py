"""AI 根因分析服务"""
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """你是一位数据质量专家。以下是某张表的字段异常信息：
- 表名: {table_name}
- 异常字段: {column_name}
- 异常类型: {metric}
- 当前值: {value_str}
- 阈值: {threshold_str}
- 异常持续天数: {duration_days}天

请分析可能的技术原因（数据源、ETL、Schema变更等），并给出1-3条可操作的修复建议。

返回JSON格式（不要包含其他内容）：
{{"root_cause": "...", "suggestions": ["建议1", "建议2"], "confidence": "high|medium|low"}}
"""


class AIGenAnalysisService:
    """AI 根因分析服务（支持 Ollama / OpenAI 双模式）"""

    def __init__(
        self,
        use_openai: bool | None = None,
        default_model: str = "qwen2.5:7b",
        openai_model: str = "gpt-4o-mini",
        openai_api_key: str = "",
    ):
        # 延迟导入避免循环依赖
        from api.config import get_settings
        settings = get_settings()
        cfg = settings.ai_analysis

        self._use_openai = use_openai if use_openai is not None else cfg.use_openai
        self._default_model = default_model or cfg.default_model
        self._openai_model = openai_model or cfg.openai_model
        self._openai_api_key = openai_api_key or cfg.openai_api_key

    @property
    def _model(self) -> str:
        return self._openai_model if self._use_openai else self._default_model

    def _build_prompt(
        self,
        table_name: str,
        column_name: str,
        metric: str,
        value: float,
        threshold: float,
        duration_days: int,
    ) -> str:
        # 格式化值
        if metric in ("null_rate", "distinct_rate", "negative_rate"):
            value_str = f"{value * 100:.1f}%"
            threshold_str = f"{threshold * 100:.1f}%"
        else:
            value_str = f"{value}"
            threshold_str = f"{threshold}"

        prompt = PROMPT_TEMPLATE.format(
            table_name=table_name,
            column_name=column_name,
            metric=metric,
            value_str=value_str,
            threshold_str=threshold_str,
            duration_days=duration_days,
        )
        return prompt

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        text = raw.strip()
        # 去除 markdown code fence
        for fence in ("```json", "```JSON", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
            if text.endswith(fence):
                text = text[: -len(fence)]
        text = text.strip()
        try:
            data = json.loads(text)
            return {
                "root_cause": str(data.get("root_cause", "")),
                "suggestions": list(data.get("suggestions", [])),
                "confidence": str(data.get("confidence", "low")),
            }
        except json.JSONDecodeError:
            logger.warning("LLM response is not valid JSON: %s", raw[:100])
            return {"root_cause": "", "suggestions": [], "confidence": "low"}

    def analyze(
        self,
        table_name: str,
        column_name: str,
        metric: str,
        value: float,
        threshold: float,
        duration_days: int,
    ) -> dict[str, Any]:
        """执行根因分析，返回解析后的结果"""
        prompt = self._build_prompt(
            table_name, column_name, metric, value, threshold, duration_days
        )
        if self._use_openai:
            raw = self._call_openai(prompt)
        else:
            raw = self._call_ollama(prompt)
        result = self._parse_response(raw)
        result["model_used"] = "openai" if self._use_openai else "ollama"
        return result

    def _call_ollama(self, prompt: str) -> str:
        from services.ai.ollama_service import OllamaService
        svc = OllamaService(model=self._default_model)
        result = svc.generate(prompt)
        return result

    def _call_openai(self, prompt: str) -> str:
        if not self._openai_api_key:
            raise ValueError("OpenAI API key not configured")
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 512,
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
