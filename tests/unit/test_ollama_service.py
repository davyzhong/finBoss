"""OllamaService 单元测试（使用 http_client 注入简化 mock）"""
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_client(post_response: dict | None = None, get_response: dict | None = None, status_code: int = 200):
    """构建可注入的 mock AsyncClient 类。

    直接注入到 OllamaService(http_client=MockClientClass)，
    绕过 httpx 依赖，无需 patch。
    """
    import httpx

    class MockAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            # 跳过父类初始化（避免真实网络请求）
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url: str, **kw) -> httpx.Response:
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = status_code
            mock_resp.raise_for_status = MagicMock()
            if status_code >= 400:
                mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "error", request=MagicMock(), response=mock_resp
                )
            # response.json() 在 httpx>=0.26 中是 async 方法
            mock_resp.json = AsyncMock(return_value=post_response or {"message": {"content": "default"}})
            return mock_resp

        async def get(self, url: str, **kw) -> httpx.Response:
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = status_code
            mock_resp.raise_for_status = MagicMock()
            if status_code >= 400:
                mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "error", request=MagicMock(), response=mock_resp
                )
            mock_resp.json = AsyncMock(return_value=get_response or {"models": []})
            return mock_resp

    return MockAsyncClient


class TestOllamaServiceGenerate:
    """generate() 同步方法测试（内部通过 run_until_complete 调用异步实现）"""

    def test_generate_basic(self):
        """测试基本生成"""
        mock_cls = _make_mock_client(post_response={
            "message": {"content": "SELECT SUM(total_ar_amount) FROM dm.dm_ar_summary"}
        })
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = service.generate("本月应收总额是多少")
        assert "SELECT" in result

    def test_generate_with_system_prompt(self):
        """测试带系统提示词"""
        mock_cls = _make_mock_client(post_response={"message": {"content": "测试响应"}})
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = service.generate("你好", system="你是一个助手")
        assert result == "测试响应"

    def test_generate_custom_temperature(self):
        """测试自定义温度参数"""
        captured_payload: dict = {}

        class PayloadCaptureClient(_make_mock_client(post_response={"message": {"content": "ok"}})):
            async def post(self, url: str, **kw) -> MagicMock:
                captured_payload.update(kw)
                return await super().post(url, **kw)

        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=PayloadCaptureClient)
        service.generate("test", temperature=0.9)
        assert captured_payload.get("json", {}).get("temperature") == 0.9

    def test_generate_http_error_propagates(self):
        """测试 HTTP 错误被正确抛出"""
        import httpx
        mock_cls = _make_mock_client(post_response={}, status_code=500)
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        with pytest.raises(httpx.HTTPStatusError):
            service.generate("test")


class TestOllamaServiceAvailability:
    """is_available() 方法测试"""

    def test_is_available_true(self):
        """测试服务可用"""
        mock_cls = _make_mock_client(get_response={"models": []})
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        assert service.is_available() is True

    def test_is_available_false_on_error(self):
        """测试连接失败返回 False"""
        import httpx

        class FailingClient(_make_mock_client()):

            async def get(self, url: str, **kw) -> MagicMock:
                raise httpx.ConnectError("failed")

        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=FailingClient)
        assert service.is_available() is False


class TestOllamaServiceListModels:
    """list_models() 方法测试"""

    def test_list_models_success(self):
        """测试成功列出模型"""
        mock_cls = _make_mock_client(get_response={
            "models": [
                {"name": "qwen2.5:7b", "size": 4700000000},
                {"name": "nomic-embed-text", "size": 274000000},
            ]
        })
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = service.list_models()
        assert len(result) == 2
        assert result[0]["name"] == "qwen2.5:7b"

    def test_list_models_error_returns_empty(self):
        """测试网络错误返回空列表"""
        import httpx

        class FailingClient(_make_mock_client()):

            async def get(self, url: str, **kw) -> MagicMock:
                raise httpx.ConnectError("failed")

        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=FailingClient)
        assert service.list_models() == []


class TestOllamaServiceAsyncMethods:
    """agenerate / ais_available 异步方法直接测试"""

    @pytest.mark.asyncio
    async def test_agenerate(self):
        """测试异步生成方法"""
        mock_cls = _make_mock_client(post_response={"message": {"content": "async response"}})
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = await service.agenerate("test")
        assert result == "async response"

    @pytest.mark.asyncio
    async def test_ais_available(self):
        """测试异步可用性检查"""
        mock_cls = _make_mock_client(get_response={"models": []})
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = await service.ais_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_alist_models(self):
        """测试异步列出模型"""
        mock_cls = _make_mock_client(get_response={"models": [{"name": "test-model"}]})
        from services.ai.ollama_service import OllamaService
        service = OllamaService(http_client=mock_cls)
        result = await service.alist_models()
        assert len(result) == 1
        assert result[0]["name"] == "test-model"
