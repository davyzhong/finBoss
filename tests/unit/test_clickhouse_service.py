"""ClickHouseDataService 单元测试"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from services.clickhouse_service import (
    ClickHouseDataService,
    _validate_limit,
    _validate_table_name,
)


class TestValidateLimit:
    """_validate_limit() 边界校验"""

    def test_none_returns_default(self):
        assert _validate_limit(None) == 100

    def test_valid_positive_int(self):
        assert _validate_limit(50) == 50
        assert _validate_limit(1) == 1
        assert _validate_limit(10000) == 10000

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            _validate_limit(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            _validate_limit(-1)

    def test_over_max_raises(self):
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            _validate_limit(10001)

    def test_non_integer_raises(self):
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            _validate_limit("100")  # type: ignore
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            _validate_limit(3.14)  # type: ignore


class TestValidateTableName:
    """_validate_table_name() 表名白名单校验"""

    def test_valid_prefixes(self):
        assert _validate_table_name("std.std_ar") == "std.std_ar"
        assert _validate_table_name("raw.kingdee_ar") == "raw.kingdee_ar"
        assert _validate_table_name("dm.dm_ar_summary") == "dm.dm_ar_summary"

    def test_case_insensitive(self):
        assert _validate_table_name("STD.std_ar") == "STD.std_ar"
        assert _validate_table_name("Raw.KingdeeAR") == "Raw.KingdeeAR"
        assert _validate_table_name("DM.DM_AR_SUMMARY") == "DM.DM_AR_SUMMARY"

    def test_system_table_rejected(self):
        with pytest.raises(ValueError, match="table_name must start with one of"):
            _validate_table_name("system.query_log")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="table_name must be a string"):
            _validate_table_name(123)  # type: ignore


class TestClickHouseDataServiceExecuteQuery:
    """execute_query() 方法测试"""

    def test_returns_dict_list(self):
        """验证返回值是 dict 列表"""
        mock_client = MagicMock()

        def fake_execute(sql, params=None, **kwargs):
            return (
                [("2026-03-01", 100000.0), ("2026-03-02", 200000.0)],
                [("stat_date", "String"), ("total_ar_amount", "Float64")],
            )

        mock_client.execute = fake_execute

        svc = ClickHouseDataService(client=mock_client)
        result = svc.execute_query("SELECT stat_date, total_ar_amount FROM dm.dm_ar_summary")

        assert len(result) == 2
        assert result[0]["stat_date"] == "2026-03-01"
        assert result[1]["total_ar_amount"] == 200000.0

    def test_empty_result_returns_empty_list(self):
        """空结果返回空列表"""
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        result = svc.execute_query("SELECT * FROM dm.dm_ar_summary LIMIT 0")
        assert result == []

    def test_params_passed_to_client(self):
        """验证 params 参数正确传递"""
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        svc.execute_query("SELECT * FROM dm.dm_ar_summary WHERE company_code = %(code)s", {"code": "C001"})

        mock_client.execute.assert_called_once()
        args, kwargs = mock_client.execute.call_args
        # params 是第二个位置参数
        assert args[1] == {"code": "C001"}
        # with_column_types 是关键字参数
        assert kwargs.get("with_column_types") is True


class TestClickHouseDataServiceGetARSummary:
    """get_ar_summary() 方法测试"""

    def test_calls_correct_sql(self):
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        svc.get_ar_summary()

        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        sql = call_args[0][0]
        assert "dm.dm_ar_summary" in sql
        assert "SELECT" in sql.upper()

    def test_with_company_code_filter(self):
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        svc.get_ar_summary(company_code="C001")

        args, kwargs = mock_client.execute.call_args
        # params 是 execute_query 的第二个位置参数
        assert args[1] == {"company_code": "C001"}

    def test_with_stat_date_filter(self):
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        svc.get_ar_summary(stat_date="2026-03-01")

        args, kwargs = mock_client.execute.call_args
        assert args[1] == {"stat_date": "2026-03-01"}


class TestClickHouseDataServiceGetLatestETLTime:
    """get_latest_etl_time() 方法测试"""

    def test_valid_table(self):
        """有效表名返回 datetime"""
        mock_client = MagicMock()
        mock_client.execute.return_value = (
            [(datetime(2026, 3, 21, 12, 0, 0),)],
            [("latest_etl_time",)],
        )

        svc = ClickHouseDataService(client=mock_client)
        result = svc.get_latest_etl_time("dm.dm_ar_summary")

        assert result == datetime(2026, 3, 21, 12, 0, 0)

    def test_invalid_table_raises(self):
        """非法表名抛出 ValueError"""
        mock_client = MagicMock()

        svc = ClickHouseDataService(client=mock_client)
        with pytest.raises(ValueError, match="table_name must start with one of"):
            svc.get_latest_etl_time("system.query_log")

    def test_none_result_returns_now(self):
        """无结果时返回当前时间"""
        mock_client = MagicMock()
        mock_client.execute.return_value = ([], [])

        svc = ClickHouseDataService(client=mock_client)
        result = svc.get_latest_etl_time("raw.kingdee_ar")

        assert result is not None
        assert isinstance(result, datetime)
