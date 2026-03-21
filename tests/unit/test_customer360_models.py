# tests/unit/test_customer360_models.py
"""测试客户360数据模型"""
from decimal import Decimal

import pytest

from schemas.customer360 import (
    Customer360Record,
    CustomerMergeQueue,
    Customer360Summary,
    CustomerDistribution,
    CustomerTrend,
    MatchAction,
    MatchResult,
    MergeHistory,
    RawARRecord,
    RawCustomer,
)


class TestRawCustomer:
    def test_required_fields_only(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
        )
        assert c.source_system == "kingdee"
        assert c.customer_id == "K001"
        assert c.customer_name == "腾讯科技"
        assert c.customer_short_name is None
        assert c.etl_time is not None

    def test_all_fields(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
            customer_short_name="腾讯",
            tax_id="91440300MA5D12345X",
            credit_code="91440300MA5D12345X",
            address="深圳南山区",
            contact="张三",
            phone="13800138000",
        )
        assert c.tax_id == "91440300MA5D12345X"
        assert c.credit_code == "91440300MA5D12345X"

    def test_etl_time_auto_now(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        assert c.etl_time is not None


class TestMatchResult:
    def test_auto_merge_result(self):
        customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        result = MatchResult(
            action=MatchAction.AUTO_MERGE,
            customers=[customer],
            unified_customer_code="C360_abc123",
            similarity=1.0,
            reason="名称完全相同",
        )
        assert result.action == MatchAction.AUTO_MERGE
        assert result.unified_customer_code == "C360_abc123"

    def test_pending_result(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技（深圳）")
        result = MatchResult(
            action=MatchAction.PENDING,
            customers=[c1, c2],
            similarity=0.91,
            reason="名称相似度 0.91",
        )
        assert result.action == MatchAction.PENDING
        assert result.unified_customer_code is None


class TestCustomerMergeQueue:
    def test_default_status_is_pending(self):
        customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        match = MatchResult(
            action=MatchAction.PENDING,
            customers=[customer],
            similarity=0.9,
            reason="test",
        )
        q = CustomerMergeQueue(id="mq_001", match_result=match)
        assert q.status == "pending"
        assert q.operator is None
        assert q.operated_at is None

    def test_all_status_values(self):
        for status in ["pending", "confirmed", "rejected", "auto_merged"]:
            customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
            match = MatchResult(
                action=MatchAction.AUTO_MERGE if status == "auto_merged" else MatchAction.PENDING,
                customers=[customer],
                similarity=1.0,
                reason="test",
            )
            q = CustomerMergeQueue(id="mq_001", match_result=match, status=status)
            assert q.status == status


class TestCustomer360Record:
    def test_required_fields(self):
        from datetime import date
        from datetime import datetime as dt
        record = Customer360Record(
            unified_customer_code="C360_abc123",
            raw_customer_ids=["K001", "K002"],
            source_systems=["kingdee"],
            customer_name="腾讯",
            ar_total=Decimal("100000"),
            ar_overdue=Decimal("5000"),
            overdue_rate=0.05,
            payment_score=85.0,
            risk_level="低",
            merge_status="auto_merged",
            stat_date=date(2025, 3, 21),
            updated_at=dt.now(),
        )
        assert record.unified_customer_code == "C360_abc123"
        assert record.risk_level == "低"
        assert record.payment_score == 85.0


class TestCustomer360Summary:
    def test_all_fields(self):
        summary = Customer360Summary(
            total_customers=100,
            merged_customers=5,
            pending_merges=2,
            ar_total=Decimal("1000000"),
            ar_overdue_total=Decimal("50000"),
            overall_overdue_rate=5.0,
            risk_distribution={"高": 3, "中": 10, "低": 87},
            concentration_top10_ratio=0.35,
        )
        assert summary.total_customers == 100
        assert summary.overall_overdue_rate == 5.0
        assert summary.top10_ar_customers == []
