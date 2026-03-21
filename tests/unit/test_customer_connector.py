# tests/unit/test_customer_connector.py
"""测试 ERP 客户连接器"""
from datetime import date
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
