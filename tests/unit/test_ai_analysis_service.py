"""AI 分析服务单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestAIGenAnalysisService:
    def test_build_prompt_includes_context(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        prompt = svc._build_prompt(
            table_name="std.std_ar",
            column_name="ar_amount",
            metric="null_rate",
            value=0.35,
            threshold=0.20,
            duration_days=5,
        )
        assert "std.std_ar" in prompt
        assert "ar_amount" in prompt
        assert "35.0%" in prompt or "35%" in prompt

    def test_parse_llm_response_valid_json(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        raw = '{"root_cause":"数据源导出问题","suggestions":["检查上游接口","修复ETL任务"],"confidence":"high"}'
        result = svc._parse_response(raw)
        assert result["root_cause"] == "数据源导出问题"
        assert len(result["suggestions"]) == 2
        assert result["confidence"] == "high"

    def test_parse_llm_response_with_markdown_fence(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        raw = '```json\n{"root_cause":"test","suggestions":["a"],"confidence":"medium"}\n```'
        result = svc._parse_response(raw)
        assert result["root_cause"] == "test"

    def test_parse_llm_response_invalid_json(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        result = svc._parse_response("not json at all")
        assert result["root_cause"] == ""
        assert result["confidence"] == "low"

    def test_ollama_mode_default(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService(use_openai=False)
        assert svc._use_openai is False
        assert svc._model == "qwen2.5:7b"

    @patch("services.ai_analysis_service.httpx.Client")
    def test_analyze_calls_openai(self, mock_http_client_cls):
        from services.ai_analysis_service import AIGenAnalysisService
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"root_cause":"upstream bug","suggestions":["fix"],"confidence":"high"}'}}]
        }
        mock_http_client_cls.return_value = mock_instance
        svc = AIGenAnalysisService(use_openai=True, openai_api_key="test-key")
        result = svc.analyze(
            table_name="std.std_ar",
            column_name="ar_amount",
            metric="null_rate",
            value=0.35,
            threshold=0.20,
            duration_days=5,
        )
        mock_instance.post.assert_called_once()
        assert result["root_cause"] == "upstream bug"
        assert result["model_used"] == "openai"

    @patch("services.ai.ollama_service.OllamaService")
    def test_analyze_calls_ollama(self, mock_ollama_cls):
        from services.ai_analysis_service import AIGenAnalysisService
        mock_instance = MagicMock()
        mock_instance.generate.return_value = '{"root_cause":"test","suggestions":["a"],"confidence":"medium"}'
        mock_ollama_cls.return_value = mock_instance
        svc = AIGenAnalysisService(use_openai=False)
        result = svc.analyze(
            table_name="std.std_ar",
            column_name="ar_amount",
            metric="null_rate",
            value=0.35,
            threshold=0.20,
            duration_days=5,
        )
        mock_instance.generate.assert_called_once()
        assert result["root_cause"] == "test"
        assert result["model_used"] == "ollama"
