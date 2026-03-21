"""测试归因分析服务"""
from unittest.mock import patch

from schemas.attribution import AttributionResult
from services.ai.attribution_service import AttributionService, calc_confidence


class TestCalcConfidence:
    def test_empty_result_returns_zero(self):
        assert calc_confidence([], "customer") == 0.0

    def test_single_row_adds_base_score(self):
        result = [{"overdue_amount": 100}]
        confidence = calc_confidence(result, "customer")
        assert confidence >= 0.3

    def test_many_rows_adds_extra_score(self):
        result = [{"v": i} for i in range(10)]
        confidence = calc_confidence(result, "time")
        assert confidence >= 0.5  # 0.3 base + 0.2 for > 5 rows

    def test_varying_values_adds_variation_score(self):
        result = [{"v": 1}, {"v": 1000}, {"v": 2000}]
        confidence = calc_confidence(result, "customer")
        assert confidence >= 0.6  # 0.3 + 0.3 (variation) = 0.6

    def test_constant_values_no_variation_score(self):
        result = [{"v": 100}, {"v": 100}, {"v": 100}]
        confidence = calc_confidence(result, "customer")
        assert confidence == 0.3  # Only base score

    def test_confidence_capped_at_one(self):
        result = [{"v": 1}, {"v": 2}, {"v": 3}, {"v": 10000}, {"v": 20000}, {"v": 30000}]
        confidence = calc_confidence(result, "time")
        assert confidence <= 1.0


class TestAttributionService:
    @patch("services.ai.attribution_service.OllamaService")
    @patch("services.ai.attribution_service.ClickHouseDataService")
    def test_analyze_returns_result(self, mock_ch, mock_ollama):
        mock_ollama.return_value.generate.return_value = '{"hypotheses": []}'
        mock_ch.return_value.execute_query.return_value = []
        service = AttributionService()
        result = service.analyze("为什么本月逾期率上升了")
        assert isinstance(result, AttributionResult)
        assert result.question == "为什么本月逾期率上升了"
        assert result.analysis_time >= 0
