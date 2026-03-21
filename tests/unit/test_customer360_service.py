# tests/unit/test_customer360_service.py
"""测试客户360核心服务"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from schemas.customer360 import (
    Customer360Record,
    MatchAction,
    MatchResult,
    RawARRecord,
    RawCustomer,
)
from services.customer360_service import (
    Customer360Generator,
    Customer360Service,
    PaymentScoreCalculator,
    RiskLevelCalculator,
)


class TestPaymentScoreCalculator:
    def setup_method(self):
        self.calc = PaymentScoreCalculator()

    def test_no_records_returns_50(self):
        score = self.calc.calculate([])
        assert score == 50.0

    def test_full_payment_no_overdue(self):
        records = [
            self._make_ar(is_overdue=False, bill_date=date.today(), overdue_days=0)
            for _ in range(10)
        ]
        score = self.calc.calculate(records)
        assert score == 100.0

    def test_all_overdue_high_rate(self):
        records = [self._make_ar(is_overdue=True, overdue_days=10) for _ in range(10)]
        score = self.calc.calculate(records)
        assert score == 0.0

    def test_score_bounded_0_100(self):
        records = [self._make_ar(is_overdue=True, overdue_days=200) for _ in range(100)]
        score = self.calc.calculate(records)
        assert 0.0 <= score <= 100.0

    def _make_ar(self, is_overdue: bool, overdue_days: int = 0, bill_date: date | None = None) -> RawARRecord:
        if bill_date is None:
            bill_date = date(2025, 1, 1)
        return RawARRecord(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯",
            bill_no=f"AR{overdue_days}",
            bill_date=bill_date,
            due_date=bill_date,
            bill_amount=Decimal("1000"),
            received_amount=Decimal("0"),
            is_overdue=is_overdue,
            overdue_days=overdue_days,
            company_code="C001",
        )


class TestRiskLevelCalculator:
    def setup_method(self):
        self.calc = RiskLevelCalculator()

    def test_high_risk_overdue_rate_above_30_percent(self):
        level = self.calc.calculate(score=50.0, overdue_rate=0.35)
        assert level == "高"

    def test_high_risk_low_score(self):
        level = self.calc.calculate(score=30.0, overdue_rate=0.1)
        assert level == "高"

    def test_medium_risk(self):
        level = self.calc.calculate(score=60.0, overdue_rate=0.15)
        assert level == "中"

    def test_low_risk(self):
        level = self.calc.calculate(score=80.0, overdue_rate=0.05)
        assert level == "低"


class TestCustomer360Generator:
    def setup_method(self):
        self.gen = Customer360Generator()

    def test_generate_from_auto_merge(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技")
        match = MatchResult(
            action=MatchAction.AUTO_MERGE,
            customers=[c1, c2],
            unified_customer_code="C360_abc123",
            similarity=1.0,
            reason="名称完全相同",
        )
        records = self.gen.generate_from_match([match], stat_date=date(2025, 3, 21))
        assert len(records) == 1
        assert records[0].unified_customer_code == "C360_abc123"
        assert records[0].merge_status == "auto_merged"

    def test_generate_from_pending_yields_nothing(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技（深圳）")
        match = MatchResult(
            action=MatchAction.PENDING,
            customers=[c1, c2],
            similarity=0.91,
            reason="名称相似度 0.91",
        )
        records = self.gen.generate_from_match([match], stat_date=date(2025, 3, 21))
        assert len(records) == 0

    def test_generate_with_ar_aggregates_amounts(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯")
        match = MatchResult(
            action=MatchAction.AUTO_MERGE,
            customers=[c1, c2],
            unified_customer_code="C360_abc123",
            similarity=1.0,
            reason="名称完全相同",
        )
        ar1 = self._make_ar(customer_id="K001", bill_amount=Decimal("5000"))
        ar2 = self._make_ar(customer_id="K002", bill_amount=Decimal("3000"))
        records = self.gen.generate_from_match(
            [match],
            ar_by_customer={"K001": [ar1], "K002": [ar2]},
            stat_date=date(2025, 3, 21),
        )
        assert len(records) == 1
        assert records[0].ar_total == Decimal("8000")
        assert records[0].raw_customer_ids == ["K001", "K002"]

    def _make_ar(self, customer_id: str, bill_amount: Decimal) -> RawARRecord:
        return RawARRecord(
            source_system="kingdee",
            customer_id=customer_id,
            customer_name="腾讯",
            bill_no=f"AR{customer_id}",
            bill_date=date(2025, 1, 1),
            due_date=date(2025, 1, 1),
            bill_amount=bill_amount,
            received_amount=Decimal("0"),
            is_overdue=False,
            overdue_days=0,
            company_code="C001",
        )
