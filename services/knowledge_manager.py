"""知识库版本管理服务"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from api.config import get_settings
from schemas.attribution import KnowledgeDoc, KnowledgeListResult

logger = logging.getLogger(__name__)

PRODUCTION_ALIAS = "finboss_knowledge"
STAGING_NAME = "finboss_knowledge_v2"


class KnowledgeManager:
    """知识库版本管理服务"""

    def __init__(self):
        settings = get_settings()
        self.host = settings.milvus.host
        self.port = settings.milvus.port
        self.collection_name = settings.milvus.collection_name
        self._embedding_url = "http://localhost:11434/api/embeddings"

    def connect(self) -> None:
        connections.connect(host=self.host, port=self.port)

    def migrate_collection(self) -> None:
        """
        幂等迁移：Phase 2 → v2（带版本字段）
        使用 Alias 实现零停机原子切换。
        """
        # 1. 检查是否已完成迁移（幂等）
        try:
            alias = utility.get_collection_alias(PRODUCTION_ALIAS)
            if alias == STAGING_NAME:
                logger.info("Migration already completed, skipping.")
                return
        except Exception:
            pass  # 别名不存在，继续迁移

        # 2. 创建 v2 集合（含版本字段）
        self._create_versioned_collection(STAGING_NAME)

        # 3. 迁移 Phase 2 数据（如存在）
        try:
            old_collection = Collection("finboss_knowledge")
            old_collection.load()
            results = old_collection.query(
                expr="is_active == true || version > 0",
                output_fields=["id", "content", "vector", "category", "metadata"],
            )
            self._migrate_docs_to_v2(results)
        except Exception as e:
            logger.warning(f"Phase 2 data not found, skipping migration: {e}")

        # 4. 原子切换别名
        try:
            utility.drop_alias(PRODUCTION_ALIAS)
        except Exception:
            pass
        utility.create_alias(STAGING_NAME, PRODUCTION_ALIAS)
        logger.info("Migration completed successfully.")

    def _create_versioned_collection(self, name: str, dimension: int = 768) -> None:
        """创建含版本字段的集合"""
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="version", dtype=DataType.INT32, default_value=1),
            FieldSchema(name="created_at", dtype=DataType.DATETIME),
            FieldSchema(name="updated_at", dtype=DataType.DATETIME),
            FieldSchema(name="is_active", dtype=DataType.BOOL, default_value=True),
            FieldSchema(name="change_log", dtype=DataType.VARCHAR, max_length=1024),
        ]
        schema = CollectionSchema(fields=fields, description="FinBoss Knowledge Base v2")
        collection = Collection(name=name, schema=schema)
        collection.create_index(
            field_name="vector",
            index_params={"index_type": "IVF_FLAT", "metric_type": "L2", "params": {"nlist": 128}},
        )
        collection.load()

    def _migrate_docs_to_v2(self, docs: list[dict]) -> None:
        """将 Phase 2 文档迁移到 v2 集合"""
        if not docs:
            return
        collection = Collection(STAGING_NAME)
        now = datetime.now()
        for doc in docs:
            entities = [
                [doc["id"]],
                [doc["content"]],
                [doc["vector"]],
                [doc.get("category", "general")],
                [json.dumps(doc.get("metadata", {}), ensure_ascii=False)],
                [1],  # version
                [now],  # created_at
                [now],  # updated_at
                [True],  # is_active
                ["从 Phase 2 迁移"],
            ]
            collection.insert(entities)
        collection.flush()

    def _generate_embedding(self, text: str) -> list[float]:
        import httpx

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    self._embedding_url,
                    json={"model": "nomic-embed-text", "prompt": text},
                )
                if response.status_code == 200:
                    return response.json().get("embedding", [])
        except Exception:
            pass

        # Fallback: 假向量（仅 POC）
        hash_bytes = hashlib.sha256(text.encode()).digest()
        dim = 768
        return [float(hash_bytes[i % len(hash_bytes)] % 256) / 255.0 for i in range(dim)]

    def _get_collection(self) -> Collection:
        self.connect()
        if not utility.has_collection(self.collection_name):
            raise ValueError(f"Collection {self.collection_name} not found")
        collection = Collection(self.collection_name)
        collection.load()
        return collection

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> KnowledgeListResult:
        """分页查询知识库（仅活跃文档）"""
        self.connect()

        expr = "is_active == true"
        if category:
            expr = f'{expr} AND category == "{category}"'

        collection = self._get_collection()
        offset = (page - 1) * page_size

        results = collection.query(
            expr=expr,
            output_fields=[
                "id",
                "content",
                "category",
                "metadata",
                "version",
                "created_at",
                "updated_at",
                "is_active",
                "change_log",
            ],
            limit=page_size,
            offset=offset,
        )

        # 统计总数
        all_results = collection.query(
            expr=expr,
            output_fields=["id"],
        )
        total = len(all_results)

        items = [self._dict_to_doc(r) for r in results]
        return KnowledgeListResult(items=items, total=total, page=page, page_size=page_size)

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        """获取单个文档（最新活跃版本）"""
        self.connect()
        collection = self._get_collection()

        results = collection.query(
            expr=f'id == "{doc_id}" AND is_active == true',
            output_fields=[
                "id",
                "content",
                "category",
                "metadata",
                "version",
                "created_at",
                "updated_at",
                "is_active",
                "change_log",
            ],
            limit=1,
        )
        if not results:
            return None
        return self._dict_to_doc(results[0])

    def create(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc:
        """创建文档（版本=1）"""
        self.connect()
        collection = self._get_collection()

        doc_id = f"kb_{hashlib.md5(content.encode()).hexdigest()[:12]}"
        now = datetime.now()
        vector = self._generate_embedding(content)
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        entities = [
            [doc_id],
            [content],
            [vector],
            [category],
            [meta_str],
            [1],
            [now],
            [now],
            [True],
            [change_log],
        ]
        collection.insert(entities)
        collection.flush()

        return KnowledgeDoc(
            id=doc_id,
            content=content,
            category=category,
            metadata=metadata or {},
            version=1,
            created_at=now,
            updated_at=now,
            is_active=True,
            change_log=change_log,
        )

    def update(
        self,
        doc_id: str,
        content: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc | None:
        """更新文档（生成新版本）"""
        self.connect()
        collection = self._get_collection()

        # 获取当前版本
        current = collection.query(
            expr=f'id == "{doc_id}" AND is_active == true',
            output_fields=["id", "content", "category", "metadata", "version", "created_at"],
            limit=1,
        )
        if not current:
            return None

        cur = current[0]
        new_version = int(cur.get("version", 1)) + 1
        new_content = content if content is not None else cur.get("content", "")
        new_category = category if category is not None else cur.get("category", "general")

        # 软删除旧版本
        collection.update(
            expr=f'id == "{doc_id}" AND is_active == true',
            data={"is_active": False},
        )

        # 插入新版本
        now = datetime.now()
        vector = self._generate_embedding(new_content)
        new_meta = metadata if metadata is not None else json.loads(cur.get("metadata", "{}"))

        entities = [
            [doc_id],
            [new_content],
            [vector],
            [new_category],
            [json.dumps(new_meta, ensure_ascii=False)],
            [new_version],
            [cur.get("created_at", now)],
            [now],
            [True],
            [change_log],
        ]
        collection.insert(entities)
        collection.flush()

        return KnowledgeDoc(
            id=doc_id,
            content=new_content,
            category=new_category,
            metadata=new_meta,
            version=new_version,
            created_at=cur.get("created_at", now),
            updated_at=now,
            is_active=True,
            change_log=change_log,
        )

    def delete(self, doc_id: str, change_log: str = "") -> bool:
        """软删除文档"""
        self.connect()
        collection = self._get_collection()
        try:
            collection.update(
                expr=f'id == "{doc_id}" AND is_active == true',
                data={"is_active": False, "change_log": change_log or "deleted"},
            )
            collection.flush()
            return True
        except Exception:
            return False

    def get_history(self, doc_id: str) -> list[KnowledgeDoc]:
        """获取文档版本历史"""
        self.connect()
        collection = self._get_collection()
        results = collection.query(
            expr=f'id == "{doc_id}"',
            output_fields=[
                "id",
                "content",
                "category",
                "metadata",
                "version",
                "created_at",
                "updated_at",
                "is_active",
                "change_log",
            ],
            limit=100,
        )
        return sorted(
            [self._dict_to_doc(r) for r in results], key=lambda d: d.version, reverse=True
        )

    def rollback(self, doc_id: str, target_version: int, change_log: str = "") -> KnowledgeDoc | None:
        """回滚到指定版本（生成新版本，内容来自历史版本）"""
        history = self.get_history(doc_id)
        target = next((d for d in history if d.version == target_version), None)
        if not target:
            return None

        return self.update(
            doc_id=doc_id,
            content=target.content,
            category=target.category,
            metadata=target.metadata,
            change_log=change_log or f"rollback to version {target_version}",
        )

    def _dict_to_doc(self, d: dict) -> KnowledgeDoc:
        meta = d.get("metadata", "{}")
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
        return KnowledgeDoc(
            id=d.get("id", ""),
            content=d.get("content", ""),
            category=d.get("category", "general"),
            metadata=meta,
            version=int(d.get("version", 1)),
            created_at=d.get("created_at", datetime.now()),
            updated_at=d.get("updated_at", datetime.now()),
            is_active=d.get("is_active", True),
            change_log=d.get("change_log", ""),
        )
