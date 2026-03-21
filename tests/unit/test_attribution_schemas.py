"""测试归因数据模型"""
import pytest
from schemas.attribution import Factor, AttributionResult


def test_factor_model():
    factor = Factor(
        dimension="customer",
        description="大客户账期延长",
        contribution=0.65,
        evidence={"top_customer": "阿里巴巴", "delta": 4800000},
        confidence=0.8,
        suggestion="建议与该客户对账并催收",
    )
    assert factor.dimension == "customer"
    assert factor.confidence == 0.8


def test_attribution_result_model():
    result = AttributionResult(
        question="为什么本月逾期率上升了",
        factors=[],
        overall_confidence=0.75,
        analysis_time=12.5,
    )
    assert result.question == "为什么本月逾期率上升了"
    assert result.overall_confidence == 0.75


def test_factor_dimension_literal_rejects_product():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Factor(
            dimension="product",  # Not allowed in Phase 3
            description="test",
            contribution=0.5,
            evidence={},
            confidence=0.5,
            suggestion="test",
        )


def test_knowledge_doc_model():
    from datetime import datetime
    from schemas.attribution import KnowledgeDoc

    now = datetime.now()
    doc = KnowledgeDoc(
        id="kb_test123",
        content="测试内容",
        category="financial_accounting",
        metadata={"author": "admin"},
        version=2,
        created_at=now,
        updated_at=now,
        is_active=True,
        change_log="updated",
    )
    assert doc.id == "kb_test123"
    assert doc.version == 2
    assert doc.is_active is True


def test_knowledge_doc_defaults():
    from datetime import datetime
    from schemas.attribution import KnowledgeDoc

    now = datetime.now()
    doc = KnowledgeDoc(
        id="kb_abc",
        content="内容",
        category="general",
        created_at=now,
        updated_at=now,
    )
    assert doc.version == 1
    assert doc.is_active is True
    assert doc.change_log == ""
    assert doc.metadata == {}


def test_knowledge_list_result_model():
    from datetime import datetime
    from schemas.attribution import KnowledgeDoc, KnowledgeListResult

    now = datetime.now()
    doc = KnowledgeDoc(
        id="kb_xyz",
        content="test",
        category="general",
        created_at=now,
        updated_at=now,
    )
    result = KnowledgeListResult(
        items=[doc],
        total=1,
        page=1,
        page_size=20,
    )
    assert len(result.items) == 1
    assert result.total == 1
    assert result.page == 1
