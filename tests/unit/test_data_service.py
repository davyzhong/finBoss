# tests/unit/test_data_service.py
"""DataService 单元测试"""
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest
from services.data_service import DataService


class TestDataService:
    @pytest.fixture
    def mock_engine(self):
        return MagicMock()

    @pytest.fixture
    def data_service(self, mock_engine):
        with patch("services.data_service.get_settings"):
            return DataService(engine=mock_engine)

    def test_execute_query(self, data_service, mock_engine):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = [(1, "test1"), (2, "test2")]
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = data_service.execute_query("SELECT * FROM test")
        assert len(result) == 2
        assert result[0] == {"id": 1, "name": "test1"}

    def test_get_ar_summary(self, data_service, mock_engine):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.keys.return_value = ["company_code", "total_ar_amount"]
        mock_result.fetchall.return_value = [("C001", 1000000.0)]
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = data_service.get_ar_summary()
        assert len(result) == 1
        assert result[0]["company_code"] == "C001"

    def test_get_customer_ar(self, data_service, mock_engine):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.keys.return_value = ["customer_code", "total_ar_amount"]
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = data_service.get_customer_ar(is_overdue=True)
        assert isinstance(result, list)

    def test_execute_non_select_rejected(self, data_service):
        # 测试注入防护
        with pytest.raises(Exception):
            data_service.execute_query("DROP TABLE test")
