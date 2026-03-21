# tests/unit/test_customer_standardizer.py
"""测试客户数据标准化"""
import pytest

from schemas.customer360 import RawCustomer
from services.customer_standardizer import CustomerStandardizer


class TestCustomerStandardizer:
    def setup_method(self):
        self.std = CustomerStandardizer()

    def test_removes_spaces(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="深圳 腾讯 计算机",
        )
        result = self.std.standardize(c)
        assert " " not in result.customer_name

    def test_removes_parentheses(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯计算机（深圳）有限公司",
        )
        result = self.std.standardize(c)
        assert "（" not in result.customer_name
        assert "(" not in result.customer_name

    def test_removes_common_suffixes(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技有限公司",
        )
        result = self.std.standardize(c)
        assert "有限公司" not in result.customer_name

    def test_short_name_first_4_chars(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="深圳市腾讯计算机系统有限公司",
        )
        result = self.std.standardize(c)
        assert result.customer_short_name == "深圳市腾"

    def test_short_name_short_name(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯",
        )
        result = self.std.standardize(c)
        assert result.customer_short_name == "腾讯"

    def test_preserves_original_fields(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
            address="深圳",
            contact="张三",
        )
        result = self.std.standardize(c)
        assert result.customer_id == "K001"
        assert result.source_system == "kingdee"
        assert result.address == "深圳"
        assert result.contact == "张三"

    def test_returns_new_instance(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
        )
        result = self.std.standardize(c)
        assert result is not c
        assert c.customer_name == "腾讯科技"  # 原始不变
