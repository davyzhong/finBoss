"""知识库管理 API 路由"""
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from schemas.attribution import KnowledgeDoc, KnowledgeListResult
from services.knowledge_manager import KnowledgeManager

router = APIRouter()


def _manager() -> KnowledgeManager:
    return KnowledgeManager()


@router.get("", response_model=KnowledgeListResult)
async def list_knowledge(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = None,
) -> KnowledgeListResult:
    """分页查询知识库文档"""
    return _manager().list(page=page, page_size=page_size, category=category)


@router.post("", response_model=KnowledgeDoc)
async def create_knowledge(
    content: str,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
    change_log: str = "",
) -> KnowledgeDoc:
    """创建知识文档"""
    return _manager().create(
        content=content,
        category=category,
        metadata=metadata,
        change_log=change_log,
    )


@router.get("/{doc_id}", response_model=KnowledgeDoc)
async def get_knowledge(doc_id: str) -> KnowledgeDoc:
    """获取单个文档"""
    doc = _manager().get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{doc_id}", response_model=KnowledgeDoc)
async def update_knowledge(
    doc_id: str,
    content: str | None = None,
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
    change_log: str = "",
) -> KnowledgeDoc:
    """更新文档（生成新版本）"""
    doc = _manager().update(
        doc_id=doc_id,
        content=content,
        category=category,
        metadata=metadata,
        change_log=change_log,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_knowledge(doc_id: str, change_log: str = "") -> dict[str, Any]:
    """软删除文档"""
    success = _manager().delete(doc_id, change_log=change_log)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": doc_id, "status": "deleted"}


@router.get("/{doc_id}/history", response_model=list[KnowledgeDoc])
async def get_history(doc_id: str) -> list[KnowledgeDoc]:
    """获取版本历史"""
    return _manager().get_history(doc_id)


@router.post("/{doc_id}/rollback", response_model=KnowledgeDoc)
async def rollback(doc_id: str, target_version: int, change_log: str = "") -> KnowledgeDoc:
    """回滚到指定版本"""
    doc = _manager().rollback(doc_id, target_version, change_log=change_log)
    if not doc:
        raise HTTPException(status_code=404, detail="Version not found")
    return doc
