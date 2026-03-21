"""知识管理 API 集成测试"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from schemas.attribution import KnowledgeDoc, KnowledgeListResult


@pytest.fixture
def mock_knowledge_manager():
    """Mock KnowledgeManager to avoid Milvus dependency in tests."""
    with patch("api.routes.knowledge.KnowledgeManager") as mock_km:
        instance = MagicMock()
        mock_km.return_value = instance

        # Mock list response
        mock_list = KnowledgeListResult(
            items=[
                KnowledgeDoc(
                    id="doc-1",
                    content="测试文档内容",
                    category="test",
                    version=1,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    is_active=True,
                )
            ],
            total=1,
            page=1,
            page_size=20,
        )
        instance.list.return_value = mock_list

        # Mock get response
        instance.get.return_value = KnowledgeDoc(
            id="doc-1",
            content="测试文档内容",
            category="test",
            version=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
        )

        # Mock create response
        instance.create.return_value = KnowledgeDoc(
            id="new-doc-id",
            content="新文档",
            category="test",
            version=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
        )

        # Mock update response
        instance.update.return_value = KnowledgeDoc(
            id="doc-1",
            content="更新后的内容",
            category="test",
            version=2,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
        )

        # Mock delete response
        instance.delete.return_value = True

        # Mock history response
        instance.get_history.return_value = [
            KnowledgeDoc(
                id="doc-1",
                content="版本1",
                category="test",
                version=1,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                is_active=True,
            ),
            KnowledgeDoc(
                id="doc-1",
                content="版本2",
                category="test",
                version=2,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                is_active=True,
            ),
        ]

        # Mock rollback response
        instance.rollback.return_value = KnowledgeDoc(
            id="doc-1",
            content="回滚后的内容",
            category="test",
            version=3,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
        )

        yield instance


@pytest.fixture
def client():
    return TestClient(create_app())


class TestKnowledgeListEndpoint:
    """GET /api/v1/ai/knowledge - 分页查询知识库文档"""

    def test_list_returns_200_with_mock(self, client, mock_knowledge_manager):
        """测试列表查询返回200"""
        r = client.get("/api/v1/ai/knowledge")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_list_pagination_params(self, client, mock_knowledge_manager):
        """测试分页参数"""
        r = client.get("/api/v1/ai/knowledge?page=2&page_size=10")
        assert r.status_code == 200
        mock_knowledge_manager.list.assert_called_once()
        call_args = mock_knowledge_manager.list.call_args
        assert call_args.kwargs["page"] == 2
        assert call_args.kwargs["page_size"] == 10

    def test_list_category_filter(self, client, mock_knowledge_manager):
        """测试分类过滤"""
        r = client.get("/api/v1/ai/knowledge?category=finance")
        assert r.status_code == 200
        mock_knowledge_manager.list.assert_called_once()
        assert mock_knowledge_manager.list.call_args.kwargs["category"] == "finance"


class TestKnowledgeCreateEndpoint:
    """POST /api/v1/ai/knowledge - 创建知识文档"""

    def test_create_returns_200(self, client, mock_knowledge_manager):
        """测试创建文档返回200和文档对象"""
        r = client.post(
            "/api/v1/ai/knowledge",
            params={
                "content": "测试文档内容",
                "category": "test",
                "change_log": "test create",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "content" in data
        assert "category" in data


class TestKnowledgeGetEndpoint:
    """GET /api/v1/ai/knowledge/{doc_id} - 获取单个文档"""

    def test_get_returns_200(self, client, mock_knowledge_manager):
        """测试获取文档返回200"""
        r = client.get("/api/v1/ai/knowledge/doc-1")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "doc-1"

    def test_get_not_found_returns_404(self, client, mock_knowledge_manager):
        """测试文档不存在返回404"""
        mock_knowledge_manager.get.return_value = None
        r = client.get("/api/v1/ai/knowledge/nonexistent-id")
        assert r.status_code == 404


class TestKnowledgeUpdateEndpoint:
    """PUT /api/v1/ai/knowledge/{doc_id} - 更新文档"""

    def test_update_returns_200(self, client, mock_knowledge_manager):
        """测试更新文档返回200"""
        r = client.put(
            "/api/v1/ai/knowledge/doc-1",
            params={
                "content": "更新后的内容",
                "change_log": "update content",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == 2

    def test_update_not_found_returns_404(self, client, mock_knowledge_manager):
        """测试更新不存在的文档返回404"""
        mock_knowledge_manager.update.return_value = None
        r = client.put(
            "/api/v1/ai/knowledge/nonexistent-id",
            params={"content": "new content"},
        )
        assert r.status_code == 404


class TestKnowledgeDeleteEndpoint:
    """DELETE /api/v1/ai/knowledge/{doc_id} - 删除文档"""

    def test_delete_returns_200(self, client, mock_knowledge_manager):
        """测试软删除返回200"""
        r = client.delete("/api/v1/ai/knowledge/doc-1", params={"change_log": "delete"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "deleted"

    def test_delete_not_found_returns_404(self, client, mock_knowledge_manager):
        """测试删除不存在的文档返回404"""
        mock_knowledge_manager.delete.return_value = False
        r = client.delete("/api/v1/ai/knowledge/nonexistent-id")
        assert r.status_code == 404


class TestKnowledgeHistoryEndpoint:
    """GET /api/v1/ai/knowledge/{doc_id}/history - 获取版本历史"""

    def test_history_returns_200(self, client, mock_knowledge_manager):
        """测试获取版本历史返回200"""
        r = client.get("/api/v1/ai/knowledge/doc-1/history")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2


class TestKnowledgeRollbackEndpoint:
    """POST /api/v1/ai/knowledge/{doc_id}/rollback - 回滚到指定版本"""

    def test_rollback_returns_200(self, client, mock_knowledge_manager):
        """测试回滚返回200"""
        r = client.post(
            "/api/v1/ai/knowledge/doc-1/rollback",
            params={"target_version": 1, "change_log": "rollback to v1"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data

    def test_rollback_not_found_returns_404(self, client, mock_knowledge_manager):
        """测试回滚到不存在的版本返回404"""
        mock_knowledge_manager.rollback.return_value = None
        r = client.post(
            "/api/v1/ai/knowledge/doc-1/rollback",
            params={"target_version": 99},
        )
        assert r.status_code == 404
