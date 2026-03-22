# tests/conftest.py
"""pytest 配置和 fixtures"""
import os
from datetime import datetime, timedelta

import pytest
from factory.random import reseed_random

TEST_API_KEY = "test-secret-key-for-integration-tests"

from api.config import Settings, get_settings
from api.dependencies import (
    get_alert_service,
    get_attribution_service,
    get_clickhouse_service,
    get_nl_query_service,
    get_quality_service,
    get_rag_service,
)
from schemas.dm.ar import DMARSummary
from schemas.std.ar import StdARRecord


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """设置测试环境"""
    reseed_random(42)


@pytest.fixture(autouse=True)
def clear_service_caches():
    """每个测试前清除所有服务缓存，确保测试隔离"""
    for fn in (
        get_clickhouse_service,
        get_quality_service,
        get_rag_service,
        get_nl_query_service,
        get_attribution_service,
        get_alert_service,
    ):
        fn.cache_clear()
    yield
    for fn in (
        get_clickhouse_service,
        get_quality_service,
        get_rag_service,
        get_nl_query_service,
        get_attribution_service,
        get_alert_service,
    ):
        fn.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """获取测试配置"""
    return get_settings()


@pytest.fixture
def sample_ar_records() -> list[StdARRecord]:
    """样例 AR 记录"""
    now = datetime.now()
    return [
        StdARRecord(
            id="rec-001",
            stat_date=now,
            company_code="C001",
            company_name="测试公司A",
            customer_code="CU001",
            customer_name="客户A",
            bill_no="AR20260301001",
            bill_date=now - timedelta(days=10),
            due_date=now - timedelta(days=5),
            bill_amount=100000.0,
            received_amount=30000.0,
            allocated_amount=20000.0,
            unallocated_amount=50000.0,
            currency="CNY",
            exchange_rate=1.0,
            bill_amount_base=100000.0,
            received_amount_base=30000.0,
            aging_bucket="0-30",
            aging_days=10,
            is_overdue=False,
            overdue_days=0,
            status="A",
            document_status="C",
            employee_name="张三",
            dept_name="销售部",
            etl_time=now,
        ),
        StdARRecord(
            id="rec-002",
            stat_date=now,
            company_code="C001",
            company_name="测试公司A",
            customer_code="CU002",
            customer_name="客户B",
            bill_no="AR20260301002",
            bill_date=now - timedelta(days=45),
            due_date=now - timedelta(days=40),
            bill_amount=50000.0,
            received_amount=0.0,
            allocated_amount=0.0,
            unallocated_amount=50000.0,
            currency="CNY",
            exchange_rate=1.0,
            bill_amount_base=50000.0,
            received_amount_base=0.0,
            aging_bucket="31-60",
            aging_days=45,
            is_overdue=True,
            overdue_days=5,
            status="A",
            document_status="C",
            employee_name="李四",
            dept_name="销售部",
            etl_time=now,
        ),
        StdARRecord(
            id="rec-003",
            stat_date=now,
            company_code="C001",
            company_name="测试公司A",
            customer_code="CU001",
            customer_name="客户A",
            bill_no="AR20260301003",
            bill_date=now - timedelta(days=100),
            due_date=now - timedelta(days=95),
            bill_amount=200000.0,
            received_amount=100000.0,
            allocated_amount=50000.0,
            unallocated_amount=50000.0,
            currency="CNY",
            exchange_rate=1.0,
            bill_amount_base=200000.0,
            received_amount_base=100000.0,
            aging_bucket="91-180",
            aging_days=100,
            is_overdue=True,
            overdue_days=5,
            status="A",
            document_status="C",
            employee_name="张三",
            dept_name="销售部",
            etl_time=now,
        ),
    ]


@pytest.fixture
def sample_dm_summary() -> DMARSummary:
    """样例数据集市汇总"""
    return DMARSummary(
        stat_date=datetime.now(),
        company_code="C001",
        company_name="测试公司A",
        total_ar_amount=350000.0,
        received_amount=130000.0,
        allocated_amount=70000.0,
        unallocated_amount=150000.0,
        overdue_amount=100000.0,
        overdue_count=2,
        total_count=3,
        overdue_rate=0.6667,
        aging_0_30=50000.0,
        aging_31_60=50000.0,
        aging_61_90=0.0,
        aging_91_180=50000.0,
        aging_180_plus=0.0,
        etl_time=datetime.now(),
    )
