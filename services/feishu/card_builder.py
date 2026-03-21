"""飞书交互卡片构建器"""
from typing import Any


class CardBuilder:
    """飞书卡片模板构建器"""

    @staticmethod
    def _fmt_currency(amount: float) -> str:
        """格式化货币显示"""
        return f"¥{amount:,.2f}"

    @staticmethod
    def _fmt_rate(rate: float) -> str:
        """格式化百分比"""
        return f"{rate * 100:.1f}%"

    @staticmethod
    def _fmt_delta(delta: float, is_negative_good: bool = False) -> str:
        """格式化变化值（带 emoji）"""
        if delta > 0:
            emoji = "↓" if is_negative_good else "↑"
            return f"{emoji}{abs(delta):,.2f}"
        elif delta < 0:
            emoji = "↑" if is_negative_good else "↓"
            return f"{emoji}{abs(delta):,.2f}"
        return "—"

    def query_result_card(self, query: str, result: dict[str, Any]) -> dict[str, Any]:
        """NL 查询结果卡片"""
        elements = [
            {"tag": "markdown", "content": f"**📋 查询**: {query}"},
            {"tag": "hr"},
        ]

        if result.get("success"):
            explanation = result.get("explanation", "查询完成")
            elements.append({"tag": "markdown", "content": explanation})

            if result.get("sql"):
                elements.append(
                    {
                        "tag": "markdown",
                        "content": f"```sql\n{result['sql']}\n```",
                    }
                )
        else:
            error = result.get("error", "未知错误")
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"❌ **错误**: {error}",
                }
            )

        # 操作按钮
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📋 查看详情"},
                        "type": "primary",
                        "value": '{"action": "view_detail"}',
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔄 重新查询"},
                        "type": "default",
                        "value": '{"action": "retry"}',
                    },
                ],
            }
        )

        return {"header": {"title": {"tag": "plain_text", "content": "📊 FinBoss 查询结果"}, "template": "blue"}, "elements": elements}

    def attribution_card(self, result: dict[str, Any]) -> dict[str, Any]:
        """归因分析结果卡片"""
        factors = result.get("factors", [])
        overall_conf = result.get("overall_confidence", 0)

        elements = [
            {
                "tag": "markdown",
                "content": f"**🔍 归因分析**: {result.get('question', '')}",
            },
            {"tag": "hr"},
        ]

        if factors:
            for i, factor in enumerate(factors[:3], 1):
                dim_emoji = "👤" if factor.get("dimension") == "customer" else "📅"
                conf = factor.get("confidence", 0)
                conf_bar = "█" * int(conf * 5) + "░" * (5 - int(conf * 5))
                elements.append(
                    {
                        "tag": "markdown",
                        "content": (
                            f"{i}. {dim_emoji} **{factor.get('description', '')}**\n"
                            f"   置信度: {conf_bar} {conf:.0%}\n"
                            f"   建议: {factor.get('suggestion', '—')}"
                        ),
                    }
                )
        else:
            elements.append({"tag": "markdown", "content": "⚠️ 未能生成分析结果，请检查数据"})

        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "markdown",
                "content": f"⏱️ 分析耗时: {result.get('analysis_time', 0):.1f}s | 置信度: {overall_conf:.0%}",
            }
        )

        return {
            "header": {"title": {"tag": "plain_text", "content": "🔬 归因分析报告"}, "template": "purple"},
            "elements": elements,
        }

    def summary_card(self, summary_data: dict[str, Any]) -> dict[str, Any]:
        """AR 汇总报告卡片"""
        elements = [
            {"tag": "markdown", "content": "## 📊 应收账款汇总报告"},
            {"tag": "hr"},
        ]

        kpis = [
            ("应收总额", self._fmt_currency(summary_data.get("total_ar_amount", 0)), "blue"),
            ("已收金额", self._fmt_currency(summary_data.get("received_amount", 0)), "green"),
            ("逾期金额", self._fmt_currency(summary_data.get("overdue_amount", 0)), "red"),
            ("逾期率", self._fmt_rate(summary_data.get("overdue_rate", 0)), "red" if summary_data.get("overdue_rate", 0) > 0.2 else "green"),
        ]

        for label, value, color in kpis:
            elements.append(
                {
                    "tag": "column_set",
                    "flex_mode": "border_center",
                    "columns": [
                        {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [{"tag": "markdown", "content": label}]},
                        {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [{"tag": "markdown", "content": f"**{value}**"}]},
                    ],
                }
            )

        elements.append(
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📈 趋势分析"}, "type": "primary", "value": '{"action": "trend"}'},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "👤 客户分析"}, "type": "default", "value": '{"action": "customer"}'},
                ],
            }
        )

        return {"header": {"title": {"tag": "plain_text", "content": "💰 FinBoss 财务助手"}, "template": "blue"}, "elements": elements}

    def error_card(self, message: str) -> dict[str, Any]:
        """错误提示卡片"""
        return {
            "header": {"title": {"tag": "plain_text", "content": "❌ 出错了"}, "template": "red"},
            "elements": [
                {"tag": "markdown", "content": message},
                {"tag": "hr"},
                {"tag": "markdown", "content": "请稍后重试，或联系管理员。"},
            ],
        }
