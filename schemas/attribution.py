"""归因分析和知识库管理数据模型"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ============= 归因分析模型 =============


class Factor(BaseModel):
    """单个归因因子"""

    dimension: Literal["customer", "time"] = Field(description="分析维度")
    description: str = Field(description="归因描述")
    contribution: float = Field(description="贡献度（0-1）")
    evidence: dict = Field(description="支撑数据")
    confidence: float = Field(description="置信度（0-1）")
    suggestion: str = Field(description="建议措施")


class AttributionResult(BaseModel):
    """归因分析结果"""

    question: str = Field(description="用户原始问题")
    factors: list[Factor] = Field(description="Top 归因因子列表")
    overall_confidence: float = Field(description="整体置信度（0-1）")
    analysis_time: float = Field(description="分析耗时（秒）")
    raw_data: dict = Field(default_factory=dict, description="原始数据（调试用）")


# ============= 知识库管理模型 =============


class KnowledgeDoc(BaseModel):
    """知识库文档模型"""

    id: str
    content: str
    category: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    change_log: str = ""


class KnowledgeListResult(BaseModel):
    """知识库分页结果"""

    items: list[KnowledgeDoc]
    total: int
    page: int
    page_size: int
