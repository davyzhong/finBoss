# tests/unit/test_schemas.py
"""Schema 验证测试"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from schemas.dm.ar import DMARSummary, DMCustomerAR
from schemas.std.ar import StdARRecord
from schemas.raw.kingdee import RawARVerify


class TestStdARRecord:
    """标准层 AR 记录 Schema 测试"""

    def test_valid_record(self):
        """测试有效记录"""
        record = StdARRecord(
            id="test-001",
            stat_date=datetime.now(),
            company_code="C001",
            company_name="测试公司",
            customer_code="CU001",
            customer_name="测试客户",
            bill_no="AR20260319001",
            bill_date=datetime.now(),
            bill_amount=100000.0,
            bill_amount_base=100000.0,
            received_amount=30000.0,
            received_amount_base=30000.0,
            allocated_amount=20000.0,
            unallocated_amount=50000.0,
            aging_bucket="0-30",
            aging_days=10,
            is_overdue=False,
            status="A",
            document_status="C",
            etl_time=datetime.now(),
        )

        assert record.id == "test-001"
        assert record.bill_amount == 100000.0
        assert record.is_overdue is False

    def test_default_values(self):
        """测试默认值"""
        record = StdARRecord(
            id="test-002",
            stat_date=datetime.now(),
            company_code="C001",
            company_name="测试公司",
            customer_code="CU001",
            customer_name="测试客户",
            bill_no="AR20260319002",
            bill_date=datetime.now(),
            bill_amount=50000.0,
            bill_amount_base=50000.0,
            received_amount=0.0,
            received_amount_base=0.0,
            allocated_amount=0.0,
            unallocated_amount=50000.0,
            aging_bucket="0-30",
            aging_days=5,
            is_overdue=False,
            status="A",
            document_status="C",
            etl_time=datetime.now(),
        )

        assert record.currency == "CNY"
        assert record.exchange_rate == 1.0
        assert record.overdue_days == 0


class TestDMARSummary:
    """数据集市 AR 汇总测试"""

    def test_valid_summary(self):
        """测试有效汇总"""
        summary = DMARSummary(
            stat_date=datetime.now(),
            company_code="C001",
            company_name="测试公司",
            total_ar_amount=1000000.0,
            received_amount=300000.0,
            allocated_amount=200000.0,
            unallocated_amount=500000.0,
            overdue_amount=100000.0,
            overdue_count=5,
            total_count=20,
            overdue_rate=0.25,
            aging_0_30=200000.0,
            aging_31_60=150000.0,
            aging_61_90=100000.0,
            aging_91_180=50000.0,
            aging_180_plus=0.0,
            etl_time=datetime.now(),
        )

        assert summary.overdue_rate == 0.25
        assert summary.total_count == 20
