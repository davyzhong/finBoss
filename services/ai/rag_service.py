"""RAG (Retrieval-Augmented Generation) 服务"""

import hashlib
import logging
from typing import Any

import httpx
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from api.config import get_settings

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 知识库服务 - 基于 Milvus 向量数据库"""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        embedding_model: str | None = None,
        top_k: int | None = None,
    ):
        settings = get_settings()
        self.host = host or settings.milvus.host
        self.port = port or settings.milvus.port
        self.collection_name = collection_name or settings.milvus.collection_name
        self.embedding_model = embedding_model or settings.milvus.embedding_model
        self.top_k = top_k or settings.milvus.top_k
        self._collection: Collection | None = None

    def connect(self) -> None:
        """建立 Milvus 连接（使用默认别名）"""
        connections.connect(host=self.host, port=self.port)

    def create_collection(self, dimension: int = 768) -> None:
        """创建知识库集合（如果不存在）"""
        self.connect()

        if utility.has_collection(self.collection_name):
            return

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=1024),
        ]
        schema = CollectionSchema(fields=fields, description="FinBoss Financial Knowledge Base")
        collection = Collection(name=self.collection_name, schema=schema)

        # 创建 IVF_FLAT 索引
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 128},
        }
        collection.create_index(field_name="vector", index_params=index_params)
        collection.load()
        self._collection = collection

    def _generate_embedding(self, text: str) -> list[float]:
        """调用本地 embedding 服务获取向量

        NOTE: Phase 2 初期使用 HTTP 调用外部 embedding 服务。
        后续可替换为 sentence-transformers 本地推理。
        """
        try:
            # 尝试使用 Ollama 的 embedding API
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text},
                )
                if response.status_code == 200:
                    data = response.json()
                    embedding = data.get("embedding")
                    if embedding:
                        return embedding
        except Exception:
            pass

        # Fallback: 使用确定性 hash 生成伪向量 (POC only — RAG 质量降级)
        logger.warning("Ollama embedding API 不可用，使用伪向量替代，RAG 质量降级")
        hash_bytes = hashlib.sha256(text.encode()).digest()
        dim = 768  # nomic-embed-text dimension
        vector = []
        for i in range(dim):
            vector.append(float(hash_bytes[i % len(hash_bytes)] % 256) / 255.0)
        return vector

    def ingest(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        id_prefix: str = "kb",
    ) -> str:
        """向知识库添加文档

        Args:
            content: 文档内容
            category: 分类（财务科目/指标口径/业务规则）
            metadata: 附加元数据
            id_prefix: ID 前缀

        Returns:
            文档 ID
        """
        import json

        self.connect()

        if not utility.has_collection(self.collection_name):
            self.create_collection()

        collection = Collection(self.collection_name)
        collection.load()

        doc_id = f"{id_prefix}_{hashlib.md5(content.encode()).hexdigest()[:12]}"
        vector = self._generate_embedding(content)
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        entities = [[doc_id], [content], [vector], [category], [meta_str]]
        collection.insert(entities)
        collection.flush()

        return doc_id

    def ingest_batch(
        self,
        documents: list[dict[str, Any]],
    ) -> list[str]:
        """批量添加文档

        Args:
            documents: 文档列表 [{"content": ..., "category": ..., "metadata": ...}]

        Returns:
            文档 ID 列表
        """
        import json

        self.connect()

        if not utility.has_collection(self.collection_name):
            self.create_collection()

        collection = Collection(self.collection_name)
        collection.load()

        ids = []
        contents = []
        vectors = []
        categories = []
        meta_list = []

        for doc in documents:
            content = doc["content"]
            category = doc.get("category", "general")
            metadata = doc.get("metadata", {})
            doc_id = f"kb_{hashlib.md5(content.encode()).hexdigest()[:12]}"

            ids.append(doc_id)
            contents.append(content)
            vectors.append(self._generate_embedding(content))
            categories.append(category)
            meta_list.append(json.dumps(metadata, ensure_ascii=False))

        collection.insert([ids, contents, vectors, categories, meta_list])
        collection.flush()

        return ids

    def search(
        self,
        query: str,
        top_k: int | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """检索相关文档

        Args:
            query: 查询文本
            top_k: 返回数量
            category: 按分类过滤

        Returns:
            相关文档列表
        """
        import json

        self.connect()

        k = top_k or self.top_k

        if not utility.has_collection(self.collection_name):
            return []

        collection = Collection(self.collection_name)
        collection.load()

        query_vector = self._generate_embedding(query)

        # 构建搜索表达式
        expr = None
        if category:
            expr = f'category == "{category}"'

        results = collection.search(
            data=[query_vector],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=k,
            expr=expr,
            output_fields=["id", "content", "category", "metadata"],
        )

        hits = []
        for hits_list in results:
            for hit in hits_list:
                hits.append(
                    {
                        "id": hit.id,
                        "content": hit.entity.get("content"),
                        "category": hit.entity.get("category"),
                        "metadata": json.loads(hit.entity.get("metadata", "{}")),
                        "score": float(hit.distance),
                    }
                )
        return hits

    def is_available(self) -> bool:
        """检查 Milvus 服务是否可用"""
        try:
            connections.connect(host=self.host, port=self.port, timeout=5)
            return True
        except Exception:
            return False
