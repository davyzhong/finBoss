# tests/unit/test_quality_service.py
"""Quality Service 单元测试"""
from datetime import datetime, timedelta

import pytest

from services.quality_service import QualityLevel, QualityService


class TestQualityService:
    """质量服务测试"""

    def test_check_completeness_pass(self):
        """测试完整性检查通过"""
        service = QualityService()
        result = service.check_completeness(
            table_name="std_ar",
            total_count=100,
            null_counts={"bill_no": 0, "customer_code": 0},
            required_fields=["bill_no", "customer_code"],
        )

        assert result.passed is True
        assert result.level == QualityLevel.PASS

    def test_check_completeness_fail(self):
        """测试完整性检查失败"""
        service = QualityService()
        result = service.check_completeness(
            table_name="std_ar",
            total_count=100,
            null_counts={"bill_no": 5, "customer_code": 0},
            required_fields=["bill_no", "customer_code"],
        )

        assert result.passed is False
        assert result.level == QualityLevel.FAIL

    def test_check_uniqueness_pass(self):
        """测试唯一性检查通过"""
        service = QualityService()
        result = service.check_uniqueness(
            table_name="std_ar",
            duplicate_count=0,
            unique_key="bill_no",
        )

        assert result.passed is True
        assert result.level == QualityLevel.PASS

    def test_check_uniqueness_fail(self):
        """测试唯一性检查失败"""
        service = QualityService()
        result = service.check_uniqueness(
            table_name="std_ar",
            duplicate_count=5,
            unique_key="bill_no",
        )

        assert result.passed is False
        assert result.level == QualityLevel.FAIL

    def test_check_timeliness_pass(self):
        """测试及时性检查通过"""
        service = QualityService()
        latest_update = datetime.now() - timedelta(minutes=5)
        result = service.check_timeliness(
            table_name="std_ar",
            latest_update=latest_update,
            max_delay_minutes=10,
        )

        assert result.passed is True
        assert result.level == QualityLevel.PASS

    def test_check_timeliness_warning(self):
        """测试及时性检查警告"""
        service = QualityService()
        latest_update = datetime.now() - timedelta(minutes=15)
        result = service.check_timeliness(
            table_name="std_ar",
            latest_update=latest_update,
            max_delay_minutes=10,
        )

        assert result.passed is False
        assert result.level == QualityLevel.WARNING

    def test_check_timeliness_fail(self):
        """测试及时性检查失败（无更新时间）"""
        service = QualityService()
        result = service.check_timeliness(
            table_name="std_ar",
            latest_update=None,
            max_delay_minutes=10,
        )

        assert result.passed is False
        assert result.level == QualityLevel.FAIL

    def test_check_validity_pass(self):
        """测试有效性检查通过"""
        service = QualityService()
        result = service.check_validity(
            table_name="std_ar",
            invalid_count=2,
            total_count=100,
            field_name="bill_amount",
        )

        assert result.passed is True
        assert result.level == QualityLevel.PASS

    def test_check_validity_fail(self):
        """测试有效性检查失败"""
        service = QualityService()
        result = service.check_validity(
            table_name="std_ar",
            invalid_count=10,
            total_count=100,
            field_name="bill_amount",
        )

        assert result.passed is False
        assert result.level == QualityLevel.FAIL

    def test_get_summary(self):
        """测试汇总结果"""
        service = QualityService()
        service.add_result(
            service.check_uniqueness("std_ar", 0, "bill_no"),
        )
        service.add_result(
            service.check_timeliness(
                "std_ar", datetime.now() - timedelta(minutes=5), 10
            ),
        )

        summary = service.get_summary()

        assert summary["total_rules"] == 2
        assert summary["passed"] == 2
        assert summary["pass_rate"] == 1.0
        assert summary["overall_pass"] is True

    def test_reset(self):
        """测试重置"""
        service = QualityService()
        service.add_result(
            service.check_uniqueness("std_ar", 0, "bill_no"),
        )
        service.reset()

        summary = service.get_summary()
        assert summary["total_rules"] == 0
