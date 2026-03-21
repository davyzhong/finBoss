# tests/unit/test_customer_connector.py
"""测试 ERP 客户连接器"""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from connectors.customer.base import ERPCustomerConnector, ERPCustomerConnectorRegistry
from connectors.customer.kingdee import KingdeeCustomerConnector


class TestERPCustomerConnector:
    def test_is_abc(self):
        """验证是抽象基类，不能直接实例化"""
        with pytest.raises(TypeError):
            ERPCustomerConnector()


class TestERPCustomerConnectorRegistry:
    def test_register_and_get(self):
        class DummyConnector(ERPCustomerConnector):
            @property
            def source_system(self) -> str:
                return "dummy"

            def fetch_customers(self):
                return []

            def fetch_ar_records(self, start_date=None, end_date=None):
                return []

        ERPCustomerConnectorRegistry.register("dummy", DummyConnector)
        conn = ERPCustomerConnectorRegistry.get("dummy")
        assert conn.source_system == "dummy"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="未注册的 ERP"):
            ERPCustomerConnectorRegistry.get("unknown_erp")


class TestKingdeeCustomerConnector:
    def test_source_system_property(self):
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.host = "localhost"
            mock_settings.return_value.kingdee.port = 1433
            mock_settings.return_value.kingdee.user = "sa"
            mock_settings.return_value.kingdee.password = "password"
            mock_settings.return_value.kingdee.name = "DB"
            mock_settings.return_value.kingdee.jdbc_url = "jdbc:jtds:url"
            conn = KingdeeCustomerConnector()
            assert conn.source_system == "kingdee"

    def test_fetch_customers_returns_list(self):
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.host = "localhost"
            mock_settings.return_value.kingdee.port = 1433
            mock_settings.return_value.kingdee.user = "sa"
            mock_settings.return_value.kingdee.password = "password"
            mock_settings.return_value.kingdee.name = "DB"
            mock_settings.return_value.kingdee.jdbc_url = "url"
            with patch.object(KingdeeCustomerConnector, "_execute", return_value=[]):
                conn = KingdeeCustomerConnector()
                result = conn.fetch_customers()
                assert isinstance(result, list)

    def test_fetch_customers_maps_fields(self):
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.jdbc_url = "url"
            mock_rows = [
                {
                    "customer_id": "K001",
                    "customer_name": "腾讯科技",
                    "customer_short_name": "腾讯",
                    "address": "深圳",
                    "contact": "张三",
                    "phone": "13800138000",
                }
            ]
            with patch.object(KingdeeCustomerConnector, "_execute", return_value=mock_rows):
                conn = KingdeeCustomerConnector()
                customers = conn.fetch_customers()
                assert len(customers) == 1
                assert customers[0].customer_id == "K001"
                assert customers[0].customer_name == "腾讯科技"
                assert customers[0].customer_short_name == "腾讯"

    def test_fetch_ar_records_uses_ingester(self):
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.jdbc_url = "url"
            mock_ingester = MagicMock()
            mock_ingester.ingest_full.return_value = []
            with patch(
                "pipelines.ingestion.kingdee_ar.KingdeeARIngester",
                return_value=mock_ingester,
            ):
                conn = KingdeeCustomerConnector()
                conn.fetch_ar_records(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
                mock_ingester.ingest_full.assert_called_once_with(
                    start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31),
                )

    def test_fetch_ar_records_overdue_days_from_due_date(self):
        """due_date = bill_date + 30 days; overdue_days = max(0, today - due_date)"""
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.jdbc_url = "url"

            # Mock ingester that returns one record with fdate = today - 45 days
            # So due_date = today - 15 days, overdue_days = 15
            past_date = datetime.now() - timedelta(days=45)

            class FakeRecord:
                fcustid = 1001
                fcustname = "测试客户"
                fbillno = "AR001"
                fdate = past_date
                fbillamount = 10000.0
                fpaymentamount = 0.0
                funallocateamount = 5000.0
                fcompanyid = 1

            mock_ingester = MagicMock()
            mock_ingester.ingest_full.return_value = [FakeRecord()]

            with patch(
                "pipelines.ingestion.kingdee_ar.KingdeeARIngester",
                return_value=mock_ingester,
            ):
                conn = KingdeeCustomerConnector()
                records = conn.fetch_ar_records()

            assert len(records) == 1
            rec = records[0]
            # due_date should be fdate + 30 days = today - 15 days
            expected_due_date = (past_date + timedelta(days=30)).date()
            assert rec.due_date == expected_due_date
            # overdue_days = max(0, today - due_date) = 15
            assert rec.overdue_days == 15
            # is_overdue = funallocateamount > 0 AND overdue_days > 0
            assert rec.is_overdue is True

    def test_fetch_ar_records_not_overdue_if_within_terms(self):
        """Bill due in the future should not be overdue"""
        with patch("connectors.customer.kingdee.get_settings") as mock_settings:
            mock_settings.return_value.kingdee.jdbc_url = "url"

            # fdate = today - 10 days -> due_date = today + 20 days (not overdue)
            recent_date = datetime.now() - timedelta(days=10)

            class FakeRecord:
                fcustid = 1002
                fcustname = "另一客户"
                fbillno = "AR002"
                fdate = recent_date
                fbillamount = 5000.0
                fpaymentamount = 0.0
                funallocateamount = 5000.0
                fcompanyid = 2

            mock_ingester = MagicMock()
            mock_ingester.ingest_full.return_value = [FakeRecord()]

            with patch(
                "pipelines.ingestion.kingdee_ar.KingdeeARIngester",
                return_value=mock_ingester,
            ):
                conn = KingdeeCustomerConnector()
                records = conn.fetch_ar_records()

            assert len(records) == 1
            rec = records[0]
            # overdue_days should be 0 (due_date is in future)
            assert rec.overdue_days == 0
            # is_overdue = False because overdue_days == 0
            assert rec.is_overdue is False
