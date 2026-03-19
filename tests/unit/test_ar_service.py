# tests/unit/test_ar_service.py
"""AR Service 单元测试"""
from datetime import datetime, timedelta

import pytest

from services.ar_service import ARService
from schemas.std.ar import StdARRecord


class TestARServiceAging:
    """账龄计算测试"""

    def test_aging_0_30_days(self):
        """测试 0-30 天账龄"""
        service = ARService()
        bill_date = datetime.now() - timedelta(days=15)
        aging_days, bucket = service.calculate_aging(bill_date)

        assert aging_days == 15
        assert bucket == "0-30"

    def test_aging_31_60_days(self):
        """测试 31-60 天账龄"""
        service = ARService()
        bill_date = datetime.now() - timedelta(days=45)
        aging_days, bucket = service.calculate_aging(bill_date)

        assert aging_days == 45
        assert bucket == "31-60"

    def test_aging_61_90_days(self):
        """测试 61-90 天账龄"""
        service = ARService()
        bill_date = datetime.now() - timedelta(days=75)
        aging_days, bucket = service.calculate_aging(bill_date)

        assert aging_days == 75
        assert bucket == "61-90"

    def test_aging_91_180_days(self):
        """测试 91-180 天账龄"""
        service = ARService()
        bill_date = datetime.now() - timedelta(days=120)
        aging_days, bucket = service.calculate_aging(bill_date)

        assert aging_days == 120
        assert bucket == "91-180"

    def test_aging_180_plus_days(self):
        """测试 180+ 天账龄"""
        service = ARService()
        bill_date = datetime.now() - timedelta(days=200)
        aging_days, bucket = service.calculate_aging(bill_date)

        assert aging_days == 200
        assert bucket == "180+"


class TestARServiceOverdue:
    """逾期判断测试"""

    def test_is_overdue_with_due_date(self):
        """测试有到期日的逾期判断"""
        service = ARService()
        due_date = datetime.now() - timedelta(days=5)
        is_overdue, overdue_days = service.is_overdue(due_date, 30)

        assert is_overdue is True
        assert overdue_days == 5

    def test_is_not_overdue_with_due_date(self):
        """测试未到期的判断"""
        service = ARService()
        due_date = datetime.now() + timedelta(days=5)
        is_overdue, overdue_days = service.is_overdue(due_date, 3)

        assert is_overdue is False
        assert overdue_days == 0

    def test_is_overdue_without_due_date(self):
        """测试无到期日但账龄超30天"""
        service = ARService()
        is_overdue, overdue_days = service.is_overdue(None, 45)

        assert is_overdue is True
        assert overdue_days == 15

    def test_is_not_overdue_without_due_date(self):
        """测试无到期日但账龄未超30天"""
        service = ARService()
        is_overdue, overdue_days = service.is_overdue(None, 20)

        assert is_overdue is False
        assert overdue_days == 0


class TestARServiceSummarize:
    """汇总计算测试"""

    def test_summarize_by_company(self, sample_ar_records):
        """测试按公司汇总"""
        service = ARService()
        summary = service.summarize_by_company(sample_ar_records)

        assert summary.company_code == "C001"
        assert summary.total_count == 3
        # 3条记录，2条逾期
        assert summary.overdue_count == 2
        # 逾期率 2/3
        assert summary.overdue_rate == pytest.approx(0.6667, rel=0.01)
        # 逾期金额 = rec-002(50000) + rec-003(50000) = 100000
        assert summary.overdue_amount == 100000.0

    def test_summarize_empty_records(self):
        """测试空记录汇总"""
        service = ARService()
        summary = service.summarize_by_company([])

        assert summary.total_count == 0
        assert summary.total_ar_amount == 0.0
        assert summary.overdue_rate == 0.0

    def test_summarize_by_customer(self, sample_ar_records):
        """测试按客户汇总"""
        service = ARService()
        customer_records = [r for r in sample_ar_records if r.customer_code == "CU001"]
        summary = service.summarize_by_customer(customer_records)

        assert summary.customer_code == "CU001"
        assert summary.total_count == 2
        assert summary.overdue_count == 1  # 只有 rec-003 逾期
