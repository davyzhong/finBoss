"""AP API 集成测试"""
import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPUploadAPI:
    def test_upload_rejects_large_file(self, client):
        """文件超过 10MB 应返回 413"""
        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
        response = client.post(
            "/api/v1/ap/upload",
            files={"file": ("large.csv", io.BytesIO(large_content), "text/csv")},
        )
        assert response.status_code == 413
        assert "10MB" in response.json()["detail"]

    def test_upload_rejects_unsupported_type(self, client):
        """不支持的文件类型应返回 400"""
        response = client.post(
            "/api/v1/ap/upload",
            files={"file": ("data.pdf", io.BytesIO(b"pdf content"), "application/pdf")},
        )
        assert response.status_code == 400
        assert "csv" in response.json()["detail"].lower() or "xlsx" in response.json()["detail"].lower()

    def test_upload_valid_csv_returns_result(self, client):
        """有效 CSV 上传应返回解析结果"""
        with patch(
            "api.routes.ap.APBankStatementParser"
        ) as MockParser:
            mock_instance = MagicMock()
            MockParser.return_value = mock_instance
            mock_instance.process_upload.return_value = {
                "file": "bank_march.csv",
                "raw_saved": 10,
                "std_saved": 8,
                "parse_errors": 1,
                "errors": [{"row": 5, "reason": "invalid amount"}],
            }
            csv_content = "交易日期,收款人,金额,流水号\n2026-03-01,腾讯科技,10000,TXN001\n"
            response = client.post(
                "/api/v1/ap/upload",
                files={"file": ("bank_march.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["file"] == "bank_march.csv"
            assert data["raw_saved"] == 10
            assert data["std_saved"] == 8
            assert data["parse_errors"] == 1


class TestAPKPIAPI:
    def test_get_kpi_returns_structure(self, client):
        """KPI 端点应返回正确的结构"""
        with patch(
            "services.ap_service.APService.get_kpi"
        ) as mock_kpi:
            mock_kpi.return_value = {
                "ap_total": "1000000",
                "unsettled_total": "500000",
                "overdue_total": "100000",
                "overdue_rate": 0.10,
                "supplier_count": 20,
            }
            response = client.get("/api/v1/ap/kpi")
            assert response.status_code == 200
            data = response.json()
            assert "ap_total" in data
            assert "overdue_rate" in data
            assert "supplier_count" in data
            assert data["overdue_rate"] == 0.10


class TestAPSuppliersAPI:
    def test_get_suppliers_returns_list(self, client):
        """供应商汇总应返回列表"""
        with patch(
            "services.ap_service.APService.get_suppliers"
        ) as mock_suppliers:
            mock_suppliers.return_value = [
                {
                    "supplier_name": "腾讯科技",
                    "total_amount": 500000.0,
                    "unsettled_amount": 100000.0,
                    "overdue_amount": 0.0,
                    "record_count": 10,
                }
            ]
            response = client.get("/api/v1/ap/suppliers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["supplier_name"] == "腾讯科技"


class TestAPRecordsAPI:
    def test_get_records_returns_list(self, client):
        """AP 明细查询应返回列表"""
        with patch(
            "services.ap_service.APService.get_records"
        ) as mock_records:
            mock_records.return_value = [
                {
                    "id": "record-1",
                    "supplier_name": "腾讯科技",
                    "amount": "100000",
                    "bank_date": "2026-03-01",
                }
            ]
            response = client.get("/api/v1/ap/records")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["supplier_name"] == "腾讯科技"


class TestAPDashboardAPI:
    def test_get_dashboard_returns_kpi_and_suppliers(self, client):
        """AP 看板应返回 KPI 和供应商数据"""
        with patch(
            "services.ap_service.APService.get_kpi"
        ) as mock_kpi, patch(
            "services.ap_service.APService.get_suppliers"
        ) as mock_suppliers:
            mock_kpi.return_value = {
                "ap_total": "500000", "unsettled_total": "200000",
                "overdue_total": "50000", "overdue_rate": 0.1, "supplier_count": 5,
            }
            mock_suppliers.return_value = []
            response = client.get("/api/v1/ap/dashboard")
            assert response.status_code == 200
            data = response.json()
            assert "kpi" in data
            assert "suppliers" in data
            assert "generated_at" in data

    def test_generate_dashboard_returns_file_path(self, client):
        """生成看板应返回文件路径"""
        with patch(
            "services.ap_service.APService.generate_dashboard"
        ) as mock_gen:
            mock_gen.return_value = "/static/reports/ap_dashboard.html"
            response = client.post("/api/v1/ap/dashboard/generate")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "generated"
            assert "file" in data


class TestSalespersonMappingAPI:
    def test_list_mappings_returns_items(self, client):
        """映射列表应返回 items + total"""
        with patch(
            "services.salesperson_mapping_service.SalespersonMappingService.list_mappings"
        ) as mock_list:
            mock_list.return_value = [
                {"id": "1", "salesperson_id": "S001", "salesperson_name": "张三分"},
            ]
            response = client.get("/api/v1/salesperson/mappings")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] == 1

    def test_create_validates_salesperson_id_lowercase(self, client):
        """小写 salesperson_id 应被拒绝"""
        response = client.post(
            "/api/v1/salesperson/mappings",
            json={"salesperson_id": "s001", "salesperson_name": "张三分"},
        )
        # 服务层抛出 ValueError → 500 或 Pydantic 422
        assert response.status_code in (400, 422, 500)

    def test_create_valid_salesperson(self, client):
        """有效 salesperson_id 应创建成功"""
        with patch(
            "services.salesperson_mapping_service.SalespersonMappingService.create_mapping"
        ) as mock_create:
            mock_create.return_value = {
                "id": "new-id",
                "salesperson_id": "S001",
                "salesperson_name": "张三分",
            }
            response = client.post(
                "/api/v1/salesperson/mappings",
                json={"salesperson_id": "S001", "salesperson_name": "张三分"},
            )
            assert response.status_code == 200
            assert response.json()["salesperson_id"] == "S001"

    def test_get_customers_by_salesperson(self, client):
        """获取业务员的客户列表"""
        with patch(
            "services.salesperson_mapping_service.SalespersonMappingService.list_customers_by_salesperson"
        ) as mock_list:
            mock_list.return_value = [
                {"customer_id": "C001", "customer_name": "腾讯科技"},
            ]
            response = client.get("/api/v1/salesperson/S001/customers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["customer_name"] == "腾讯科技"
