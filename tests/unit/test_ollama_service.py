"""OllamaService 单元测试"""
from unittest.mock import MagicMock, patch

import pytest


class TestOllamaServiceGenerate:
    """generate() 方法测试"""

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_generate_basic(self, mock_settings, mock_client_cls):
        """测试基本生成"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "SELECT SUM(total_ar_amount) FROM dm.dm_ar_summary"}
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        result = service.generate("本月应收总额是多少")

        assert "SELECT" in result
        mock_client.post.assert_called_once()

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_generate_with_system_prompt(self, mock_settings, mock_client_cls):
        """测试带系统提示词的生成"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "测试响应"}
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        service.generate("你好", system="你是一个助手")

        # 验证 system prompt 被加入 messages
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        messages = payload["messages"]
        assert any(m.get("role") == "system" for m in messages)

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_generate_custom_temperature(self, mock_settings, mock_client_cls):
        """测试自定义温度参数"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "test"}}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        service.generate("test", temperature=0.5)

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["temperature"] == 0.5

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_generate_http_error(self, mock_settings, mock_client_cls):
        """测试 HTTP 错误处理"""
        import httpx

        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        with pytest.raises(httpx.HTTPStatusError):
            service.generate("test")


class TestOllamaServiceGenerateRaw:
    """generate_raw() 方法测试"""

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_generate_raw_returns_full_response(self, mock_settings, mock_client_cls):
        """测试返回完整响应"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        full_response = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "test"},
            "done": True,
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = full_response

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        result = service.generate_raw("test")

        assert result == full_response
        assert "model" in result


class TestOllamaServiceAvailability:
    """is_available() 方法测试"""

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_is_available_true(self, mock_settings, mock_client_cls):
        """测试服务可用"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        assert service.is_available() is True

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_is_available_false(self, mock_settings, mock_client_cls):
        """测试服务不可用"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        assert service.is_available() is False


class TestOllamaServiceListModels:
    """list_models() 方法测试"""

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_list_models_success(self, mock_settings, mock_client_cls):
        """测试成功列出模型"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        models_response = {
            "models": [
                {"name": "qwen2.5:7b", "size": 4700000000},
                {"name": "nomic-embed-text", "size": 274000000},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = models_response

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        result = service.list_models()

        assert len(result) == 2
        assert result[0]["name"] == "qwen2.5:7b"

    @patch("services.ai.ollama_service.httpx.Client")
    @patch("services.ai.ollama_service.get_settings")
    def test_list_models_error(self, mock_settings, mock_client_cls):
        """测试列出模型失败时返回空列表"""
        mock_settings.return_value.ollama.base_url = "http://localhost:11434"
        mock_settings.return_value.ollama.model = "qwen2.5:7b"
        mock_settings.return_value.ollama.temperature = 0.1
        mock_settings.return_value.ollama.max_tokens = 512
        mock_settings.return_value.ollama.timeout = 120

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.ollama_service import OllamaService

        service = OllamaService()
        result = service.list_models()

        assert result == []
