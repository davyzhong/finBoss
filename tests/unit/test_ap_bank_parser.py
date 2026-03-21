"""测试 APBankStatementParser"""
import io
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.ap_bank_parser import (
    APBankStatementParser,
    BankStatementRow,
    sanitize_filename,
    _esc,
    _COLUMN_RULES,
)


class TestSanitizeFilename:
    def test_removes_path_components(self):
        assert sanitize_filename("/path/to/file.csv") == "file.csv"
        assert sanitize_filename("../file.csv") == "file.csv"
        assert sanitize_filename("C:\\Windows\\file.csv") == "file.csv"
        assert sanitize_filename("file.csv") == "file.csv"

    def test_strips_special_chars(self):
        result = sanitize_filename("my file;rm -rf;.csv")
        assert ";" not in result
        assert " " not in result
        assert "rm" in result  # 'rm' is alphanumeric
        assert "rf" in result

    def test_truncates_to_255(self):
        long_name = "a" * 300 + ".csv"
        result = sanitize_filename(long_name)
        assert len(result) <= 255

    def test_preserves_extension(self):
        assert sanitize_filename("report.xlsx").endswith(".xlsx")
        assert sanitize_filename("data.CSV").endswith(".CSV")


class TestColumnMapping:
    def _parser(self):
        p = APBankStatementParser.__new__(APBankStatementParser)
        p._ch = MagicMock()
        p._payment_term_days = 30
        return p

    def test_detects_transaction_date(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额", "流水号", "摘要"]
        col_map = parser._detect_columns(header)
        assert col_map["bank_date"] == 0
        assert col_map["counterparty"] == 1
        assert col_map["amount"] == 2
        assert col_map["transaction_no"] == 3
        assert col_map["remark"] == 4

    def test_detects_accounting_date_fallback(self):
        parser = self._parser()
        header = ["记账日期", "收款人", "金额"]
        col_map = parser._detect_columns(header)
        assert col_map["bank_date"] == 0

    def test_detects_generic_date(self):
        parser = self._parser()
        header = ["日期", "收款人", "金额"]
        col_map = parser._detect_columns(header)
        assert col_map["bank_date"] == 0

    def test_partial_columns_maps_missing_as_not_present(self):
        parser = self._parser()
        header = ["日期", "收款人", "金额"]
        col_map = parser._detect_columns(header)
        assert "transaction_no" not in col_map
        assert "remark" not in col_map


class TestParseRow:
    def _parser(self):
        p = APBankStatementParser.__new__(APBankStatementParser)
        p._ch = MagicMock()
        p._payment_term_days = 30
        return p

    def test_parses_valid_row(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额", "流水号", "摘要"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2, "transaction_no": 3, "remark": 4}
        raw_row = ["2026-03-01", "腾讯科技", "10000", "TXN001", "付款"]
        result = parser._parse_row(raw_row, header, 2, col_map)
        assert result["bank_date"] == "2026-03-01"
        assert result["counterparty"] == "腾讯科技"
        assert result["amount"] == "10000"
        assert result["transaction_no"] == "TXN001"
        assert result["remark"] == "付款"
        assert result["direction"] == "OUT"

    def test_skips_direction_in(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额", "流水号", "方向"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2, "transaction_no": 3, "direction": 4}
        raw_row = ["2026-03-01", "腾讯科技", "10000", "TXN001", "IN"]
        result = parser._parse_row(raw_row, header, 2, col_map)
        assert result is None

    def test_negative_amount_becomes_positive(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        raw_row = ["2026-03-01", "腾讯科技", "-5000"]
        result = parser._parse_row(raw_row, header, 2, col_map)
        assert result["amount"] == "5000"

    def test_amount_with_commas(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        raw_row = ["2026-03-01", "腾讯科技", "1,000,000"]
        result = parser._parse_row(raw_row, header, 2, col_map)
        assert result["amount"] == "1000000"

    def test_out_direction_accepted(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额", "流水号", "方向"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2, "transaction_no": 3, "direction": 4}
        raw_row = ["2026-03-01", "腾讯科技", "10000", "TXN001", "OUT"]
        result = parser._parse_row(raw_row, header, 2, col_map)
        assert result is not None


class TestValidateRow:
    def _parser(self):
        p = APBankStatementParser.__new__(APBankStatementParser)
        p._ch = MagicMock()
        p._payment_term_days = 30
        return p

    def test_valid_row_no_errors(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        row = dict(zip(header, ["2026-03-01", "腾讯科技", "10000"]))
        errs = parser._validate_row(row, 2, col_map)
        assert len(errs) == 0

    def test_invalid_date_returns_error(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        row = dict(zip(header, ["not-a-date", "腾讯科技", "10000"]))
        errs = parser._validate_row(row, 5, col_map)
        assert len(errs) == 1
        assert errs[0]["row"] == 5
        assert "日期" in errs[0]["reason"]

    def test_invalid_amount_returns_error(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        row = dict(zip(header, ["2026-03-01", "腾讯科技", "NOT_A_NUMBER"]))
        errs = parser._validate_row(row, 3, col_map)
        assert len(errs) == 1
        assert errs[0]["row"] == 3
        assert "金额" in errs[0]["reason"]

    def test_both_invalid_returns_two_errors(self):
        parser = self._parser()
        header = ["交易日期", "收款人", "金额"]
        col_map = {"bank_date": 0, "counterparty": 1, "amount": 2}
        row = dict(zip(header, ["bad-date", "腾讯科技", "bad-amount"]))
        errs = parser._validate_row(row, 4, col_map)
        assert len(errs) == 2


class TestSupplierMatching:
    def _parser(self):
        p = APBankStatementParser.__new__(APBankStatementParser)
        p._ch = MagicMock()
        p._payment_term_days = 30
        return p

    def test_exact_match_returns_name(self):
        parser = self._parser()
        parser._ch = MagicMock()
        parser._ch.execute_query.return_value = [
            {"supplier_name": "腾讯科技"},
            {"supplier_name": "阿里巴巴"},
        ]
        result = parser._match_supplier("腾讯科技")
        assert result == "腾讯科技"

    def test_no_bracket_match_returns_stripped_name(self):
        parser = self._parser()
        parser._ch = MagicMock()
        parser._ch.execute_query.return_value = [
            {"supplier_name": "腾讯科技"},
        ]
        result = parser._match_supplier("腾讯科技（深圳）")
        assert result == "腾讯科技"

    def test_unknown_supplier_returns_original(self):
        parser = self._parser()
        parser._ch = MagicMock()
        parser._ch.execute_query.return_value = [
            {"supplier_name": "腾讯科技"},
        ]
        result = parser._match_supplier("完全不相关公司")
        assert result == "完全不相关公司"

    def test_empty_known_suppliers_returns_original(self):
        parser = self._parser()
        parser._ch = MagicMock()
        parser._ch.execute_query.return_value = []
        result = parser._match_supplier("任何公司")
        assert result == "任何公司"


class TestEscapeCH:
    def test_escape_single_quote(self):
        assert _esc("O'Brien") == "O\\'Brien"
        assert _esc("it's") == "it\\'s"

    def test_escape_no_op(self):
        assert _esc("normal") == "normal"
        assert _esc("") == ""
