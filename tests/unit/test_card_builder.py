"""Test card builder for Feishu Interactive Cards."""
from services.feishu.card_builder import CardBuilder


class TestCardBuilder:
    def setup_method(self):
        self.builder = CardBuilder()

    def test_query_result_card_structure(self):
        card = self.builder.query_result_card(
            query="本月应收总额",
            result={"success": True, "explanation": "本月应收总额为 0 元", "sql": "SELECT 1"},
        )
        assert "header" in card
        assert "elements" in card
        assert len(card["elements"]) > 0

    def test_query_result_card_error(self):
        card = self.builder.query_result_card(
            query="测试",
            result={"success": False, "error": "LLM 调用失败"},
        )
        assert "error" in str(card["elements"]).lower() or "错误" in str(card["elements"])

    def test_attribution_card_structure(self):
        card = self.builder.attribution_card(
            {
                "question": "为什么逾期率上升",
                "factors": [
                    {"dimension": "customer", "description": "大客户逾期", "confidence": 0.8, "suggestion": "催收"},
                ],
                "overall_confidence": 0.8,
                "analysis_time": 10.5,
            }
        )
        assert "header" in card
        assert card["header"]["template"] == "purple"

    def test_summary_card_structure(self):
        card = self.builder.summary_card({"total_ar_amount": 1000000, "received_amount": 800000, "overdue_amount": 200000, "overdue_rate": 0.2})
        assert "header" in card
        assert "elements" in card

    def test_error_card(self):
        card = self.builder.error_card("服务暂时不可用")
        assert card["header"]["template"] == "red"

    def test_fmt_currency(self):
        assert "¥1,234.00" in self.builder._fmt_currency(1234)
        assert "¥0.00" in self.builder._fmt_currency(0)

    def test_fmt_rate(self):
        assert "25.0%" in self.builder._fmt_rate(0.25)
        assert "0.0%" in self.builder._fmt_rate(0)
