# tests/unit/test_customer_matcher.py
"""测试客户匹配引擎"""
import pytest

from schemas.customer360 import MatchAction, RawCustomer
from services.customer_matcher import CustomerMatcher


class TestCustomerMatcher:
    def setup_method(self):
        self.matcher = CustomerMatcher()

    def test_name_similarity_identical(self):
        sim = self.matcher._name_similarity("腾讯科技", "腾讯科技")
        assert sim == 1.0

    def test_name_similarity_similar(self):
        sim = self.matcher._name_similarity("腾讯科技（深圳）有限公司", "腾讯科技有限公司")
        assert sim >= 0.8

    def test_name_similarity_different(self):
        sim = self.matcher._name_similarity("腾讯", "阿里巴巴")
        assert sim < 0.5

    def test_calc_similarity_exact_match(self):
        c1 = RawCustomer(
            source_system="kingdee", customer_id="K001",
            customer_name="腾讯", tax_id="123456789"
        )
        c2 = RawCustomer(
            source_system="kingdee", customer_id="K002",
            customer_name="腾讯", tax_id="123456789"
        )
        assert self.matcher._calc_similarity(c1, c2) == 1.0

    def test_calc_similarity_creditcode_match(self):
        c1 = RawCustomer(
            source_system="kingdee", customer_id="K001",
            customer_name="腾讯", credit_code="ABC123"
        )
        c2 = RawCustomer(
            source_system="kingdee", customer_id="K002",
            customer_name="腾讯", credit_code="ABC123"
        )
        assert self.matcher._calc_similarity(c1, c2) == 1.0

    def test_calc_similarity_no_match_fields(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里巴巴")
        sim = self.matcher._calc_similarity(c1, c2)
        assert 0.0 <= sim <= 1.0

    def test_generate_unified_code_deterministic(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        code1 = self.matcher._generate_unified_code([c])
        code2 = self.matcher._generate_unified_code([c])
        assert code1 == code2
        assert code1.startswith("C360_")

    def test_generate_unified_code_different_customers_different_codes(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里")
        code1 = self.matcher._generate_unified_code([c1])
        code2 = self.matcher._generate_unified_code([c2])
        assert code1 != code2

    def test_match_empty_list(self):
        results = self.matcher.match([])
        assert results == []

    def test_match_single_customer_no_group(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        results = self.matcher.match([c])
        assert results == []

    def test_match_identical_names_auto_merge(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯")
        results = self.matcher.match([c1, c2])
        assert len(results) == 1
        assert results[0].action == MatchAction.AUTO_MERGE
        assert len(results[0].customers) == 2
        assert results[0].unified_customer_code is not None

    def test_match_similar_names_pending(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技公司")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技有限公司")
        results = self.matcher.match([c1, c2])
        pending = [r for r in results if r.action == MatchAction.PENDING]
        assert len(pending) == 1
        assert pending[0].similarity < 0.95
        assert pending[0].similarity >= 0.85

    def test_match_different_names_ignored(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里巴巴")
        results = self.matcher.match([c1, c2])
        assert results == []

    def test_match_skips_seen_customers(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯")
        c3 = RawCustomer(source_system="kingdee", customer_id="K003", customer_name="腾讯")
        results = self.matcher.match([c1, c2, c3])
        auto_merges = [r for r in results if r.action == MatchAction.AUTO_MERGE]
        assert len(auto_merges) == 1
        # All 3 identical names are grouped together (correct transitive grouping)
        assert len(auto_merges[0].customers) == 3
