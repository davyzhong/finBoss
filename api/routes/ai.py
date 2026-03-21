"""AI API 路由 - NL Query, RAG, Ollama"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from api.dependencies import NLQueryServiceDep

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query")
async def nl_query(
    question: str,
    service: NLQueryServiceDep,
) -> dict[str, Any]:
    """自然语言查询

    将自然语言转换为 SQL 查询，返回结构化结果和自然语言解释。

    支持的查询示例:
    - "本月应收总额是多少"
    - "哪些客户逾期了"
    - "C001 公司的逾期率"
    - "逾期金额最高的客户"
    """
    result = service.query(question)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/health")
async def ai_health_check(service: NLQueryServiceDep) -> dict[str, Any]:
    """AI 服务健康检查

    检查 Ollama 和 Milvus 连接状态
    """
    return service.health_check()


@router.post("/rag/ingest")
async def rag_ingest(
    content: str,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """向知识库添加文档

    Args:
        content: 文档内容
        category: 分类 (financial_accounting/indicator_definition/business_rule)
        metadata: 附加元数据
    """
    from services.ai import RAGService

    svc = RAGService()
    doc_id = svc.ingest(content=content, category=category, metadata=metadata)
    return {"id": doc_id, "status": "ingested"}


@router.post("/rag/ingest/batch")
async def rag_ingest_batch(
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """批量向知识库添加文档

    Args:
        documents: 文档列表 [{"content": ..., "category": ..., "metadata": ...}]
    """
    from services.ai import RAGService

    svc = RAGService()
    ids = svc.ingest_batch(documents=documents)
    return {"ids": ids, "count": len(ids), "status": "ingested"}


@router.get("/rag/search")
async def rag_search(
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> dict[str, Any]:
    """检索知识库

    Args:
        query: 查询文本
        top_k: 返回数量
        category: 按分类过滤
    """
    from services.ai import RAGService

    svc = RAGService()
    results = svc.search(query=query, top_k=top_k, category=category)
    return {"results": results, "count": len(results)}
