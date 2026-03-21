"""测试 KnowledgeManager"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from schemas.attribution import KnowledgeDoc


class TestKnowledgeDocModel:
    """KnowledgeDoc 模型单元测试"""

    def test_knowledge_doc_model(self):
        doc = KnowledgeDoc(
            id="kb_test123",
            content="测试内容",
            category="test",
            metadata={"author": "tester"},
            version=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
            change_log="initial",
        )
        assert doc.id == "kb_test123"
        assert doc.content == "测试内容"
        assert doc.category == "test"
        assert doc.metadata == {"author": "tester"}
        assert doc.version == 1
        assert doc.is_active is True
        assert doc.change_log == "initial"

    def test_knowledge_doc_defaults(self):
        doc = KnowledgeDoc(
            id="kb_abc",
            content="内容",
            category="general",
            metadata={},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert doc.version == 1
        assert doc.is_active is True
        assert doc.change_log == ""


class TestKnowledgeManagerBasic:
    """KnowledgeManager 基础行为测试（mock Milvus）"""

    @pytest.fixture
    def km(self):
        """创建 KnowledgeManager 实例（mock settings）"""
        with patch("services.knowledge_manager.get_settings") as mock_settings:
            mock_settings.return_value.milvus.host = "localhost"
            mock_settings.return_value.milvus.port = 19530
            mock_settings.return_value.milvus.collection_name = "finboss_knowledge"
            from services.knowledge_manager import KnowledgeManager

            manager = KnowledgeManager()
            return manager

    def test_init_uses_settings(self, km):
        assert km.host == "localhost"
        assert km.port == 19530
        assert km.collection_name == "finboss_knowledge"

    def test_generate_embedding_fallback(self, km):
        """测试假向量 fallback（Ollama 不可用时）"""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value.status_code = 500
            vector = km._generate_embedding("测试文本")
            assert isinstance(vector, list)
            assert len(vector) == 768
            assert all(isinstance(x, float) for x in vector)

    def test_generate_embedding_success(self, km):
        """测试 Ollama 返回有效向量"""
        with patch("httpx.Client") as mock_client:
            mock_post = MagicMock()
            mock_post.status_code = 200
            mock_post.json.return_value = {"embedding": [0.1] * 768}
            mock_client.return_value.__enter__.return_value.post.return_value = mock_post
            vector = km._generate_embedding("测试文本")
            assert vector == [0.1] * 768

    def test_dict_to_doc_conversion(self, km):
        """测试字典到 KnowledgeDoc 转换"""
        now = datetime.now()
        raw = {
            "id": "kb_001",
            "content": "测试内容",
            "category": "finance",
            "metadata": '{"author": "tester", "score": 100}',
            "version": 2,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "change_log": "updated",
        }
        doc = km._dict_to_doc(raw)
        assert doc.id == "kb_001"
        assert doc.content == "测试内容"
        assert doc.category == "finance"
        assert doc.metadata == {"author": "tester", "score": 100}
        assert doc.version == 2
        assert doc.is_active is True
        assert doc.change_log == "updated"

    def test_dict_to_doc_with_string_metadata(self, km):
        """测试 metadata 字段为字符串时的转换"""
        now = datetime.now()
        raw = {
            "id": "kb_002",
            "content": "内容",
            "category": "general",
            "metadata": "{}",
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "change_log": "",
        }
        doc = km._dict_to_doc(raw)
        assert doc.metadata == {}

    def test_dict_to_doc_with_dict_metadata(self, km):
        """测试 metadata 字段已是 dict 时的转换"""
        now = datetime.now()
        raw = {
            "id": "kb_003",
            "content": "内容",
            "category": "general",
            "metadata": {"key": "value"},
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "change_log": "",
        }
        doc = km._dict_to_doc(raw)
        assert doc.metadata == {"key": "value"}

    def test_constants_defined(self):
        """测试模块常量"""
        from services.knowledge_manager import PRODUCTION_ALIAS, STAGING_NAME

        assert PRODUCTION_ALIAS == "finboss_knowledge"
        assert STAGING_NAME == "finboss_knowledge_v2"


class TestKnowledgeManagerCRUD:
    """KnowledgeManager CRUD 行为测试（mock Collection）"""

    @pytest.fixture
    def mock_connections(self):
        """Patch connections for entire test scope (auto-activated per test)."""
        from unittest.mock import patch

        with patch("services.knowledge_manager.connections") as mock:
            yield mock

    @pytest.fixture
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture
    def km(self, mock_connections):
        with patch("services.knowledge_manager.get_settings") as mock_settings:
            mock_settings.return_value.milvus.host = "localhost"
            mock_settings.return_value.milvus.port = 19530
            mock_settings.return_value.milvus.collection_name = "finboss_knowledge"
            from services.knowledge_manager import KnowledgeManager

            return KnowledgeManager()

    def test_list_returns_paginated_results(self, km, mock_collection):
        """测试 list 分页返回"""
        now = datetime.now()
        mock_collection.query.side_effect = [
            # First call: page results
            [
                {
                    "id": "kb_001",
                    "content": "内容1",
                    "category": "finance",
                    "metadata": "{}",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                    "change_log": "",
                },
            ],
            # Second call: count
            [{"id": "kb_001"}],
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            result = km.list(page=1, page_size=20)

        assert result.total == 1
        assert result.page == 1
        assert result.page_size == 20
        assert len(result.items) == 1
        assert result.items[0].id == "kb_001"

    def test_list_with_category_filter(self, km, mock_collection):
        """测试按 category 过滤"""
        mock_collection.query.side_effect = [[], []]
        with patch.object(km, "_get_collection", return_value=mock_collection):
            km.list(page=1, page_size=20, category="finance")

        # Verify the query expression includes category filter
        first_call = mock_collection.query.call_args_list[0]
        expr = first_call.kwargs.get("expr") or first_call[1].get("expr")
        assert "finance" in expr

    def test_get_returns_doc(self, km, mock_collection):
        """测试 get 返回文档"""
        now = datetime.now()
        mock_collection.query.return_value = [
            {
                "id": "kb_001",
                "content": "内容",
                "category": "general",
                "metadata": "{}",
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "change_log": "init",
            }
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            doc = km.get("kb_001")

        assert doc is not None
        assert doc.id == "kb_001"
        assert doc.version == 1

    def test_get_returns_none_when_not_found(self, km, mock_collection):
        """测试 get 找不到时返回 None"""
        mock_collection.query.return_value = []

        with patch.object(km, "_get_collection", return_value=mock_collection):
            doc = km.get("nonexistent")

        assert doc is None

    def test_create_inserts_doc(self, km, mock_collection):
        """测试 create 插入文档"""
        with patch.object(km, "_get_collection", return_value=mock_collection):
            with patch.object(km, "_generate_embedding", return_value=[0.0] * 768):
                doc = km.create(
                    content="新文档内容",
                    category="test",
                    metadata={"author": "tester"},
                    change_log="initial commit",
                )

        assert doc.id.startswith("kb_")
        assert doc.content == "新文档内容"
        assert doc.category == "test"
        assert doc.version == 1
        assert doc.is_active is True
        assert doc.change_log == "initial commit"
        mock_collection.insert.assert_called_once()
        mock_collection.flush.assert_called_once()

    def test_update_soft_deletes_old_version(self, km, mock_collection):
        """测试 update 软删除旧版本"""
        now = datetime.now()
        mock_collection.query.return_value = [
            {
                "id": "kb_001",
                "content": "旧内容",
                "category": "general",
                "metadata": "{}",
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "change_log": "",
            }
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            with patch.object(km, "_generate_embedding", return_value=[0.0] * 768):
                doc = km.update(
                    doc_id="kb_001",
                    content="新内容",
                    change_log="updated content",
                )

        assert doc.version == 2
        assert doc.content == "新内容"
        # Verify old version was soft-deleted
        update_calls = list(mock_collection.update.call_args_list)
        assert len(update_calls) >= 1
        # Verify new version was inserted
        mock_collection.insert.assert_called_once()

    def test_update_returns_none_when_not_found(self, km, mock_collection):
        """测试 update 找不到文档时返回 None"""
        mock_collection.query.return_value = []

        with patch.object(km, "_get_collection", return_value=mock_collection):
            result = km.update(doc_id="nonexistent", content="新内容")

        assert result is None

    def test_delete_soft_deletes(self, km, mock_collection):
        """测试 delete 软删除"""
        with patch.object(km, "_get_collection", return_value=mock_collection):
            result = km.delete("kb_001", change_log="deleted")

        assert result is True
        mock_collection.update.assert_called_once()
        mock_collection.flush.assert_called_once()

    def test_delete_returns_false_on_error(self, km, mock_collection):
        """测试 delete 失败时返回 False"""
        mock_collection.update.side_effect = Exception("Milvus error")

        with patch.object(km, "_get_collection", return_value=mock_collection):
            result = km.delete("kb_001")

        assert result is False

    def test_get_history_returns_all_versions(self, km, mock_collection):
        """测试 get_history 返回所有版本"""
        now = datetime.now()
        mock_collection.query.return_value = [
            {
                "id": "kb_001",
                "content": "版本2",
                "category": "general",
                "metadata": "{}",
                "version": 2,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "change_log": "",
            },
            {
                "id": "kb_001",
                "content": "版本1",
                "category": "general",
                "metadata": "{}",
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "is_active": False,
                "change_log": "",
            },
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            history = km.get_history("kb_001")

        assert len(history) == 2
        assert history[0].version == 2  # Sorted descending
        assert history[1].version == 1

    def test_rollback_creates_new_version(self, km, mock_collection):
        """测试 rollback 生成新版本"""
        now = datetime.now()
        mock_collection.query.side_effect = [
            # get_history: returns 2 versions
            [
                {
                    "id": "kb_001",
                    "content": "版本2",
                    "category": "general",
                    "metadata": "{}",
                    "version": 2,
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                    "change_log": "",
                },
                {
                    "id": "kb_001",
                    "content": "版本1内容",
                    "category": "general",
                    "metadata": "{}",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                    "is_active": False,
                    "change_log": "",
                },
            ],
            # update's _get_collection: current version
            [
                {
                    "id": "kb_001",
                    "content": "版本2",
                    "category": "general",
                    "metadata": "{}",
                    "version": 2,
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                    "change_log": "",
                },
            ],
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            with patch.object(km, "_generate_embedding", return_value=[0.0] * 768):
                doc = km.rollback("kb_001", target_version=1, change_log="rollback to v1")

        assert doc is not None
        assert doc.version == 3
        assert doc.content == "版本1内容"
        assert doc.change_log == "rollback to v1"

    def test_rollback_returns_none_for_invalid_version(self, km, mock_collection):
        """测试 rollback 目标版本不存在时返回 None"""
        now = datetime.now()
        mock_collection.query.return_value = [
            {
                "id": "kb_001",
                "content": "版本1",
                "category": "general",
                "metadata": "{}",
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "change_log": "",
            },
        ]

        with patch.object(km, "_get_collection", return_value=mock_collection):
            doc = km.rollback("kb_001", target_version=99)

        assert doc is None
