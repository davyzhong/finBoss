"""测试 PerSalespersonReportService"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from services.per_salesperson_report_service import PerSalespersonReportService


class TestPerSalespersonReportService:
    def test_collect_report_data_returns_summary(self):
        with patch(
            "services.per_salesperson_report_service.ClickHouseDataService"
        ) as mock_ch_cls, patch(
            "services.per_salesperson_report_service.SalespersonMappingService"
        ) as mock_map_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_map = MagicMock()
            mock_map_cls.return_value = mock_map

            # 业务员数据
            mock_map.list_active.return_value = [
                {"salesperson_id": "S001", "salesperson_name": "张三分"},
            ]
            # 客户列表
            mock_map.list_customers_by_salesperson.return_value = [
                {"customer_id": "C001", "customer_name": "腾讯科技"},
            ]
            # AR 数据
            mock_ch.execute_query.side_effect = [
                # AR 汇总
                [
                    {
                        "customer_name": "腾讯科技",
                        "ar_total": 1000000.0,
                        "ar_overdue": 100000.0,
                        "overdue_rate": 0.10,
                        "risk_level": "中",
                    }
                ],
                # 新增逾期
                [{"cnt": 2}],
            ]

            svc = PerSalespersonReportService()
            data = svc._collect_report_data("S001", date(2026, 3, 21), "weekly")
            assert data["customer_count"] == 1
            assert data["summary"]["ar_total"] == 1000000.0
            assert data["summary"]["overdue_rate"] == 0.10

    def test_collect_returns_empty_if_no_customers(self):
        with patch(
            "services.per_salesperson_report_service.ClickHouseDataService"
        ) as mock_ch_cls, patch(
            "services.per_salesperson_report_service.SalespersonMappingService"
        ) as mock_map_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_map = MagicMock()
            mock_map_cls.return_value = mock_map

            mock_map.list_active.return_value = [
                {"salesperson_id": "S001", "salesperson_name": "张三分"},
            ]
            mock_map.list_customers_by_salesperson.return_value = []

            svc = PerSalespersonReportService()
            data = svc._collect_report_data("S001", date(2026, 3, 21), "weekly")
            assert data["customer_count"] == 0
            assert data["summary"] == {}

    def test_generate_for_salesperson_skips_if_no_customers(self):
        with patch(
            "services.per_salesperson_report_service.ClickHouseDataService"
        ) as mock_ch_cls, patch(
            "services.per_salesperson_report_service.SalespersonMappingService"
        ) as mock_map_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_map = MagicMock()
            mock_map_cls.return_value = mock_map

            mock_map.list_active.return_value = []
            mock_map.list_customers_by_salesperson.return_value = []

            svc = PerSalespersonReportService()
            result = svc.generate_for_salesperson("S001", "weekly", today=date(2026, 3, 21))
            assert result == ""  # 无客户，跳过
