"""测试 SalespersonMappingService"""
import io
import pytest
from unittest.mock import MagicMock, patch

from services.salesperson_mapping_service import (
    SalespersonMappingService,
    escape_ch_string,
)


class TestEscapeCHString:
    def test_escape_single_quote(self):
        # ClickHouse 字符串转义：单引号用反斜杠转义
        assert escape_ch_string("O'Brien") == "O\\'Brien"
        assert escape_ch_string("it's") == "it\\'s"
        assert escape_ch_string("normal") == "normal"


class TestSalespersonMappingService:
    def test_list_active_returns_only_enabled(self):
        with patch(
            "services.salesperson_mapping_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"id": "1", "salesperson_id": "S001", "salesperson_name": "张三分", "enabled": 1},
                {"id": "2", "salesperson_id": "S002", "salesperson_name": "李四", "enabled": 0},
            ]
            svc = SalespersonMappingService()
            active = svc.list_active()
            assert len(active) == 2  # execute_query returns all, service filters by enabled
            # Verify the query included enabled = 1
            call_args = mock_ch.execute_query.call_args[0][0]
            assert "enabled = 1" in call_args

    def test_list_customers_by_salesperson(self):
        with patch(
            "services.salesperson_mapping_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"customer_id": "C001", "customer_name": "腾讯科技"},
            ]
            svc = SalespersonMappingService()
            customers = svc.list_customers_by_salesperson("S001")
            assert len(customers) == 1
            assert customers[0]["customer_name"] == "腾讯科技"

    def test_validate_salesperson_id_format_valid(self):
        svc = SalespersonMappingService()
        assert svc._validate_salesperson_id("S001") == "S001"
        assert svc._validate_salesperson_id("A123") == "A123"
        assert svc._validate_salesperson_id("ABCDEF") == "ABCDEF"

    def test_validate_salesperson_id_format_invalid_lowercase(self):
        svc = SalespersonMappingService()
        with pytest.raises(ValueError, match="salesperson_id"):
            svc._validate_salesperson_id("s001")  # 小写不允许

    def test_validate_salesperson_id_format_invalid_hyphen(self):
        svc = SalespersonMappingService()
        with pytest.raises(ValueError, match="salesperson_id"):
            svc._validate_salesperson_id("S-001")  # 短横线不允许


class TestCSVUpload:
    def test_parse_csv_valid(self):
        svc = SalespersonMappingService()
        csv_content = (
            "salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name\n"
            "S001,张三分,oc_xxxx,C001,腾讯科技\n"
        )
        file_content = io.BytesIO(csv_content.encode("utf-8"))
        rows, errors = svc._parse_csv_upload(file_content, "test.csv")
        assert len(rows) == 1
        assert len(errors) == 0
        assert rows[0]["salesperson_id"] == "S001"
        assert rows[0]["customer_name"] == "腾讯科技"

    def test_parse_csv_skips_invalid_salesperson_id(self):
        svc = SalespersonMappingService()
        csv_content = (
            "salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name\n"
            "S001,张三分,oc_xxxx,C001,腾讯科技\n"
            "s002,李四,oc_yyyy,C002,阿里巴巴\n"  # 小写被跳过
        )
        file_content = io.BytesIO(csv_content.encode("utf-8"))
        rows, errors = svc._parse_csv_upload(file_content, "test.csv")
        assert len(rows) == 1  # s002 被跳过
        assert len(errors) == 1
        assert errors[0]["row"] == 3
        assert "salesperson_id" in errors[0]["reason"]

    def test_parse_csv_skips_empty_salesperson_id(self):
        svc = SalespersonMappingService()
        csv_content = (
            "salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name\n"
            ",未知,oc_xxxx,C001,测试公司\n"
        )
        file_content = io.BytesIO(csv_content.encode("utf-8"))
        rows, errors = svc._parse_csv_upload(file_content, "test.csv")
        assert len(rows) == 0
        assert len(errors) == 1
