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
                "score_trend": "stable →",
                "overdue_count": 0,
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

    def test_update_anomaly_ignored(self, client):
        """PUT /api/v1/quality/anomalies/{id} with status=ignored returns 200."""
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

    def test_list_reports(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.list_reports"
        ) as mock_list:
            mock_list.return_value = [
                {
                    "id": "r1",
                    "stat_date": "2026-03-22",
                    "table_name": "dm.ar",
                    "total_fields": 10,
                    "anomaly_count": 2,
                    "score_pct": 80.0,
                    "generated_at": "2026-03-22T06:00:00",
                }
            ]
            resp = client.get("/api/v1/quality/reports")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["items"][0]["score_pct"] == 80.0

    def test_get_report_success(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.get_report"
        ) as mock_get, \
             patch(
                 "services.field_quality_service.FieldQualityService.list_anomalies_by_report"
             ) as mock_anomalies:
            mock_get.return_value = {
                "id": "r1",
                "stat_date": "2026-03-22",
                "table_name": "dm.ar",
                "total_fields": 10,
                "anomaly_count": 2,
                "score_pct": 80.0,
                "generated_at": "2026-03-22T06:00:00",
            }
            mock_anomalies.return_value = [
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
            resp = client.get("/api/v1/quality/reports/r1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["report"]["id"] == "r1"
            assert data["report"]["score_pct"] == 80.0
            assert len(data["anomalies"]) == 1

    def test_get_summary_includes_trend_and_overdue(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.get_summary"
        ) as mock:
            mock.return_value = {
                "stat_date": "2026-03-22",
                "total_tables": 3,
                "total_fields": 20,
                "anomaly_count": 2,
                "high_severity": 1,
                "medium_severity": 1,
                "score_pct": 90.0,
                "score_trend": "improving ↓",
                "overdue_count": 0,
                "last_check_at": "2026-03-22T06:00:00",
            }
            resp = client.get("/api/v1/quality/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["score_trend"] == "improving ↓"
            assert data["overdue_count"] == 0

    def test_list_anomalies_by_assignee(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.list_anomalies"
        ) as mock:
            mock.return_value = [
                {
                    "id": "a1",
                    "table_name": "dm.ar",
                    "column_name": "due_date",
                    "metric": "null_rate",
                    "value": 0.35,
                    "threshold": 0.20,
                    "severity": "高",
                    "status": "open",
                    "assignee": "zhangsan",
                    "detected_at": "2026-03-22T06:00:00",
                }
            ]
            resp = client.get("/api/v1/quality/anomalies?assignee=zhangsan")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["items"][0]["assignee"] == "zhangsan"
            mock.assert_called_once_with(None, 100, "zhangsan")

    def test_update_anomaly_assignee(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.update_anomaly"
        ) as mock:
            mock.return_value = None
            resp = client.put(
                "/api/v1/quality/anomalies/a1",
                json={"assignee": "lisi", "note": "assigned"},
            )
            assert resp.status_code == 200
            mock.assert_called_once_with("a1", status=None, assignee="lisi")

    def test_get_quality_history(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.get_quality_history"
        ) as mock_hist, \
             patch(
                 "services.field_quality_service.FieldQualityService.get_summary"
             ) as mock_sum, \
             patch(
                 "services.field_quality_service.FieldQualityService._compute_score_trend"
             ) as mock_trend:
            mock_hist.return_value = [
                {
                    "stat_date": "2026-03-22",
                    "score_pct": 90.0,
                    "anomaly_count": 2,
                    "high_severity": 0,
                    "medium_severity": 2,
                },
                {
                    "stat_date": "2026-03-21",
                    "score_pct": 85.0,
                    "anomaly_count": 5,
                    "high_severity": 1,
                    "medium_severity": 4,
                },
            ]
            mock_sum.return_value = {"score_pct": 90.0}
            mock_trend.return_value = "stable →"
            resp = client.get("/api/v1/quality/history?days=7")
            assert resp.status_code == 200
            data = resp.json()
            assert data["score_trend"] == "stable →"
            assert len(data["points"]) == 2

    def test_send_digest(self, client):
        with patch(
            "services.field_quality_service.FieldQualityService.send_quality_digest"
        ) as mock:
            mock.return_value = {"email_sent": 2, "dingtalk_sent": 1}
            resp = client.post("/api/v1/quality/send-digest")
            assert resp.status_code == 200
            data = resp.json()
            assert data["email_sent"] == 2
            assert data["dingtalk_sent"] == 1

    def test_analyze_anomaly_not_found(self, client):
        """分析不存在的异常应返回 404"""
        with patch(
            "services.field_quality_service.FieldQualityService.analyze_anomaly"
        ) as mock_analyze:
            mock_analyze.return_value = None
            resp = client.post("/api/v1/quality/anomalies/nonexistent-id/analyze")
            assert resp.status_code == 404

    def test_aggregated_anomalies_empty(self, client):
        """空数据时聚合视图应返回空 groups"""
        with patch(
            "services.field_quality_service.FieldQualityService.get_aggregated_anomalies"
        ) as mock_agg:
            mock_agg.return_value = {
                "groups": [],
                "total_anomalies": 0,
            }
            resp = client.get("/api/v1/quality/anomalies/aggregated?group_by=table")
            assert resp.status_code == 200
            data = resp.json()
            assert "groups" in data
            assert "total_anomalies" in data
            assert data["groups"] == []
            assert data["total_anomalies"] == 0

    def test_aggregated_anomalies_group_by_assignee(self, client):
        """按 assignee 聚合应返回列表"""
        with patch(
            "services.field_quality_service.FieldQualityService.get_aggregated_anomalies"
        ) as mock_agg:
            mock_agg.return_value = {
                "groups": [],
                "total_anomalies": 0,
            }
            resp = client.get("/api/v1/quality/anomalies/aggregated?group_by=assignee")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["groups"], list)

    def test_aggregated_anomalies_multiple_dimensions(self, client):
        """多维度组合聚合"""
        with patch(
            "services.field_quality_service.FieldQualityService.get_aggregated_anomalies"
        ) as mock_agg:
            mock_agg.return_value = {
                "groups": [],
                "total_anomalies": 0,
            }
            resp = client.get("/api/v1/quality/anomalies/aggregated?group_by=table,severity&status=open")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_anomalies"] >= 0
            assert "groups" in data
