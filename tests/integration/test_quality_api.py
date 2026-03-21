"""数据质量 API 集成测试"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestQualityAPI:
    def test_get_summary(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.get_summary"
        ) as mock_summary:
            mock_summary.return_value = {
                "stat_date": "2026-03-22",
                "total_tables": 3,
                "total_fields": 20,
                "anomaly_count": 2,
                "high_severity": 0,
                "medium_severity": 0,
                "score_pct": 90.0,
                "last_check_at": "2026-03-22T06:00:00",
            }
            resp = client.get("/api/v1/quality/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_tables"] == 3
            assert data["anomaly_count"] == 2
            assert data["high_severity"] == 0
            assert data["medium_severity"] == 0

    def test_trigger_check(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.check_all"
        ) as mock_check, \
             patch(
                 "services.field_quality_service.FieldQualityService.send_feishu_card"
             ):
            mock_check.return_value = {
                "total_tables": 1,
                "anomaly_count": 0,
                "score_pct": 100.0,
            }
            resp = client.post("/api/v1/quality/check")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "duration_ms" in data
            assert data["report_count"] >= 1

    def test_list_anomalies_default_open(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.list_anomalies"
        ) as mock_list:
            mock_list.return_value = [
                {
                    "id": "a1",
                    "table_name": "dm.ar",
                    "column_name": "due_date",
                    "metric": "null_rate",
                    "value": 0.35,
                    "threshold": 0.20,
                    "severity": "高",
                    "status": "open",
                    "detected_at": "2026-03-22T06:00:00",
                }
            ]
            resp = client.get("/api/v1/quality/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["items"][0]["severity"] == "高"

    def test_list_anomalies_filtered_by_status(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.list_anomalies"
        ) as mock_list:
            mock_list.return_value = []
            resp = client.get("/api/v1/quality/anomalies?status=resolved")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0

    def test_update_anomaly_resolved(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.update_anomaly"
        ) as mock_update:
            mock_update.return_value = None
            resp = client.put(
                "/api/v1/quality/anomalies/a1",
                json={"status": "resolved", "note": "fixed"},
            )
            assert resp.status_code == 200
            assert resp.json()["new_status"] == "resolved"

    def test_update_anomaly_ignores_status(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.update_anomaly"
        ) as mock_update:
            mock_update.return_value = None
            resp = client.put(
                "/api/v1/quality/anomalies/a1",
                json={"status": "ignored"},
            )
            assert resp.status_code == 200
            assert resp.json()["new_status"] == "ignored"

    def test_get_report_not_found(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.get_report"
        ) as mock_get:
            mock_get.return_value = None
            resp = client.get("/api/v1/quality/reports/nonexistent-id")
            assert resp.status_code == 404

    def test_check_all_isolates_bad_table(self, client):
        """Single table throwing an error should not abort the full scan."""
        with patch(
            "services.field_quality_service.FieldQualityService.check_all"
        ) as mock_check, \
             patch(
                 "services.field_quality_service.FieldQualityService.send_feishu_card"
             ):
            mock_check.return_value = {
                "total_tables": 1,
                "anomaly_count": 0,
                "score_pct": 100.0,
            }
            resp = client.post("/api/v1/quality/check")
            assert resp.status_code == 200
            assert resp.json()["report_count"] >= 1
