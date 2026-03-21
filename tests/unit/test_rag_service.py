"""RAGService 单元测试"""
from unittest.mock import MagicMock, patch

import pytest


class TestRAGServiceInit:
    """__init__() 测试"""

    @patch("services.ai.rag_service.get_settings")
    def test_init_with_defaults(self, mock_settings):
        """测试默认参数初始化"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "finboss_knowledge"
        mock_settings.return_value.milvus.embedding_model = "BAAI/bge-m3"
        mock_settings.return_value.milvus.top_k = 5

        from services.ai.rag_service import RAGService

        service = RAGService()

        assert service.host == "localhost"
        assert service.port == 19530
        assert service.collection_name == "finboss_knowledge"
        assert service.top_k == 5

    @patch("services.ai.rag_service.get_settings")
    def test_init_with_custom_params(self, mock_settings):
        """测试自定义参数初始化"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "test-model"
        mock_settings.return_value.milvus.top_k = 10

        from services.ai.rag_service import RAGService

        service = RAGService(
            host="192.168.1.1",
            port=19531,
            collection_name="custom_collection",
            top_k=20,
        )

        assert service.host == "192.168.1.1"
        assert service.port == 19531
        assert service.collection_name == "custom_collection"
        assert service.top_k == 20


class TestRAGServiceConnect:
    """connect() 测试"""

    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_connect_calls_pymilvus(self, mock_settings, mock_connections):
        """测试连接调用"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "test"
        mock_settings.return_value.milvus.top_k = 5

        from services.ai.rag_service import RAGService

        service = RAGService()
        service.connect()

        mock_connections.connect.assert_called_once_with(host="localhost", port=19530)


class TestRAGServiceGenerateEmbedding:
    """_generate_embedding() 测试"""

    @patch("services.ai.rag_service.httpx.Client")
    @patch("services.ai.rag_service.get_settings")
    def test_embedding_from_ollama_api(self, mock_settings, mock_client_cls):
        """测试从 Ollama API 获取 embedding"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        expected_vector = [0.1] * 768
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": expected_vector}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.rag_service import RAGService

        service = RAGService()
        result = service._generate_embedding("test text")

        assert result == expected_vector

    @patch("services.ai.rag_service.httpx.Client")
    @patch("services.ai.rag_service.get_settings")
    def test_embedding_fallback_on_error(self, mock_settings, mock_client_cls):
        """测试 Ollama 失败时降级到假向量"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.rag_service import RAGService

        service = RAGService()
        result = service._generate_embedding("test fallback")

        # 假向量应该是 768 维
        assert len(result) == 768
        assert all(0 <= v <= 1 for v in result)

    @patch("services.ai.rag_service.httpx.Client")
    @patch("services.ai.rag_service.get_settings")
    def test_embedding_fallback_on_empty_response(self, mock_settings, mock_client_cls):
        """测试 Ollama 返回空时降级"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # 无 embedding 字段

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.rag_service import RAGService

        service = RAGService()
        result = service._generate_embedding("test")

        # 降级到假向量
        assert len(result) == 768

    @patch("services.ai.rag_service.httpx.Client")
    @patch("services.ai.rag_service.get_settings")
    def test_embedding_deterministic(self, mock_settings, mock_client_cls):
        """测试相同文本产生相同 embedding（假向量特性）"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        # 所有请求都失败，走 fallback
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("fail")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.rag_service import RAGService

        service = RAGService()
        vec1 = service._generate_embedding("same text")
        vec2 = service._generate_embedding("same text")

        assert vec1 == vec2

    @patch("services.ai.rag_service.httpx.Client")
    @patch("services.ai.rag_service.get_settings")
    def test_embedding_different_for_different_text(self, mock_settings, mock_client_cls):
        """测试不同文本产生不同 embedding"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("fail")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from services.ai.rag_service import RAGService

        service = RAGService()
        vec1 = service._generate_embedding("text one")
        vec2 = service._generate_embedding("text two")

        assert vec1 != vec2


class TestRAGServiceIsAvailable:
    """is_available() 测试"""

    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_is_available_true(self, mock_settings, mock_connections):
        """测试服务可用"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "test"
        mock_settings.return_value.milvus.top_k = 5

        from services.ai.rag_service import RAGService

        service = RAGService()
        result = service.is_available()

        assert result is True

    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_is_available_false(self, mock_settings, mock_connections):
        """测试服务不可用"""
        mock_settings.return_value.milvus.host = "unreachable-host"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "test"
        mock_settings.return_value.milvus.embedding_model = "test"
        mock_settings.return_value.milvus.top_k = 5

        mock_connections.connect.side_effect = Exception("Connection refused")

        from services.ai.rag_service import RAGService

        service = RAGService()
        result = service.is_available()

        assert result is False


class TestRAGServiceSearch:
    """search() 测试"""

    @patch("services.ai.rag_service.Collection")
    @patch("services.ai.rag_service.utility")
    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_search_empty_when_no_collection(self, mock_settings, mock_connections, mock_utility, mock_collection_cls):
        """测试集合不存在时返回空"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "nonexistent"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_utility.has_collection.return_value = False

        from services.ai.rag_service import RAGService

        service = RAGService()
        service._generate_embedding = MagicMock(return_value=[0.1] * 768)

        result = service.search("test query")

        assert result == []

    @patch("services.ai.rag_service.Collection")
    @patch("services.ai.rag_service.utility")
    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_search_with_results(self, mock_settings, mock_connections, mock_utility, mock_collection_cls):
        """测试搜索返回结果"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "finboss_knowledge"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_utility.has_collection.return_value = True

        # Mock hit
        mock_hit = MagicMock()
        mock_hit.id = "kb_test123"
        mock_hit.entity.get.side_effect = lambda k, d=None: {
            "id": "kb_test123",
            "content": "逾期金额是...",
            "category": "indicator_definition",
            "metadata": "{}",
        }.get(k, d)
        mock_hit.distance = 0.5

        mock_results = [[mock_hit]]
        mock_collection = MagicMock()
        mock_collection.search.return_value = mock_results
        mock_collection_cls.return_value = mock_collection

        from services.ai.rag_service import RAGService

        service = RAGService()
        service._generate_embedding = MagicMock(return_value=[0.1] * 768)

        result = service.search("逾期金额")

        assert len(result) == 1
        assert result[0]["id"] == "kb_test123"
        assert result[0]["content"] == "逾期金额是..."
        assert result[0]["score"] == 0.5

    @patch("services.ai.rag_service.Collection")
    @patch("services.ai.rag_service.utility")
    @patch("services.ai.rag_service.connections")
    @patch("services.ai.rag_service.get_settings")
    def test_search_with_category_filter(self, mock_settings, mock_connections, mock_utility, mock_collection_cls):
        """测试带分类过滤的搜索"""
        mock_settings.return_value.milvus.host = "localhost"
        mock_settings.return_value.milvus.port = 19530
        mock_settings.return_value.milvus.collection_name = "finboss_knowledge"
        mock_settings.return_value.milvus.embedding_model = "nomic-embed-text"
        mock_settings.return_value.milvus.top_k = 5

        mock_utility.has_collection.return_value = True
        mock_collection = MagicMock()
        mock_collection.search.return_value = []
        mock_collection_cls.return_value = mock_collection

        from services.ai.rag_service import RAGService

        service = RAGService()
        service._generate_embedding = MagicMock(return_value=[0.1] * 768)

        service.search("test", category="business_rule")

        # 验证表达式包含分类过滤
        call_args = mock_collection.search.call_args
        expr = call_args.kwargs["expr"]
        assert "business_rule" in expr
