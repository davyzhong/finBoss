"""AI API 集成测试"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def mock_nl_query_service():
    with patch("api.dependencies.NLQueryService") as mock:
        svc = MagicMock()
        svc.query.return_value = {
            "success": True,
            "sql": "SELECT * FROM dm.dm_ar_summary",
            "result": [{"total": 100}],
            "explanation": "应收总额为 100 万元",
            "error": None,
        }
        svc.health_check.return_value = {"ollama": True, "milvus": True}
        mock.return_value = svc
        yield svc


@pytest.fixture
def client():
    return TestClient(create_app())


class TestAIHealthEndpoint:
    """GET /api/v1/ai/health 测试"""

    def test_health_all_healthy(self, client, mock_nl_query_service):
        """测试所有服务健康"""
        mock_nl_query_service.health_check.return_value = {
            "ollama": True,
            "milvus": True,
        }
        r = client.get("/api/v1/ai/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ollama"] is True
        assert data["milvus"] is True

    def test_health_ollama_down(self, client, mock_nl_query_service):
        """测试 Ollama 不可用"""
        mock_nl_query_service.health_check.return_value = {
            "ollama": False,
            "milvus": True,
        }
        r = client.get("/api/v1/ai/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ollama"] is False


class TestAIDirectRoutes:
    """直接调用路由函数的测试（不经过 HTTP）"""

    def test_nl_query_success(self, mock_nl_query_service):
        """测试 NL 查询成功"""
        mock_nl_query_service.query.return_value = {
            "success": True,
            "sql": "SELECT SUM(amount) FROM dm.dm_ar_summary",
            "result": [{"total": 1000000}],
            "explanation": "本月应收总额为 100 万元",
            "error": None,
        }

        from api.routes.ai import nl_query

        import asyncio

        async def run():
            result = await nl_query("本月应收总额是多少", mock_nl_query_service)
            assert result["success"] is True
            assert "SELECT" in result["sql"]

        asyncio.get_event_loop().run_until_complete(run())

    def test_nl_query_failure_returns_400(self, mock_nl_query_service):
        """测试 NL 查询失败返回 400"""
        mock_nl_query_service.query.return_value = {
            "success": False,
            "error": "LLM 调用失败",
            "sql": None,
            "result": None,
            "explanation": None,
        }

        from fastapi import HTTPException

        from api.routes.ai import nl_query

        import asyncio

        async def run():
            with pytest.raises(HTTPException) as exc_info:
                await nl_query("test", mock_nl_query_service)

            assert exc_info.value.status_code == 400
            assert "LLM 调用失败" in str(exc_info.value.detail)

        asyncio.get_event_loop().run_until_complete(run())

    def test_rag_ingest(self):
        """测试 RAG 文档添加"""
        mock_rag = MagicMock()
        mock_rag.ingest.return_value = "kb_test001"

        with patch("services.ai.RAGService", return_value=mock_rag):
            from api.routes.ai import rag_ingest

            import asyncio

            async def run():
                result = await rag_ingest(
                    content="测试内容",
                    category="test",
                    metadata={"key": "value"},
                )
                assert result["status"] == "ingested"
                mock_rag.ingest.assert_called_once()

            asyncio.get_event_loop().run_until_complete(run())

    def test_rag_search(self):
        """测试 RAG 搜索"""
        mock_rag = MagicMock()
        mock_rag.search.return_value = [
            {"id": "kb_001", "content": "逾期金额定义", "category": "indicator", "metadata": {}, "score": 0.5}
        ]

        with patch("services.ai.RAGService", return_value=mock_rag):
            from api.routes.ai import rag_search

            import asyncio

            async def run():
                result = await rag_search(
                    query="逾期率",
                    top_k=3,
                    category="indicator",
                )
                assert result["count"] == 1
                mock_rag.search.assert_called_once_with(query="逾期率", top_k=3, category="indicator")

            asyncio.get_event_loop().run_until_complete(run())

    def test_rag_search_with_defaults(self):
        """测试 RAG 搜索默认参数"""
        mock_rag = MagicMock()
        mock_rag.search.return_value = []

        with patch("services.ai.RAGService", return_value=mock_rag):
            from api.routes.ai import rag_search

            import asyncio

            async def run():
                await rag_search(query="test")
                mock_rag.search.assert_called_once_with(query="test", top_k=5, category=None)

            asyncio.get_event_loop().run_until_complete(run())

    def test_rag_ingest_batch(self):
        """测试批量 RAG 文档添加"""
        mock_rag = MagicMock()
        mock_rag.ingest_batch.return_value = ["kb_001", "kb_002"]

        with patch("services.ai.RAGService", return_value=mock_rag):
            from api.routes.ai import rag_ingest_batch

            import asyncio

            async def run():
                documents = [
                    {"content": "文档1", "category": "cat1"},
                    {"content": "文档2", "category": "cat2"},
                ]
                result = await rag_ingest_batch(documents=documents)
                assert result["count"] == 2
                assert result["status"] == "ingested"
                mock_rag.ingest_batch.assert_called_once_with(documents=documents)

            asyncio.get_event_loop().run_until_complete(run())
