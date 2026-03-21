"""归因分析服务"""
import json
import logging
import re
import time
from typing import Any

from schemas.attribution import AttributionResult, Factor
from services.ai.ollama_service import OllamaService
from services.ai.prompts import ATTRIBUTION_SYSTEM_PROMPT
from services.clickhouse_service import ClickHouseDataService

logger = logging.getLogger(__name__)


def calc_confidence(sql_result: list[dict], dimension: str) -> float:
    """基于 SQL 结果集质量计算置信度（不依赖特定字段名）"""
    if not sql_result:
        return 0.0

    score = 0.3  # 有数据

    if len(sql_result) > 5:
        score += 0.2

    # 取所有数值字段的极值（通用方法）
    all_values: list[float] = []
    for row in sql_result:
        for v in row.values():
            if isinstance(v, (int, float)):
                all_values.append(abs(float(v)))

    if all_values:
        max_val = max(all_values)
        min_val = min(all_values)
        avg_val = sum(all_values) / len(all_values)
        # 有变化（不为常数集）：+0.3
        if max_val != min_val:
            score += 0.3
        # 变化幅度显著（极值/均值 > 3）：+0.2
        if avg_val != 0 and max(abs(max_val), abs(min_val)) / avg_val > 3:
            score += 0.2

    return min(score, 1.0)


# SQL 模板（用于归因验证）
# 使用 ClickHouse param() 语法避免字符串拼接注入
SQL_TEMPLATES = {
    "customer": """
SELECT
    curr.customer_name,
    curr.overdue_amount AS overdue_amount_curr,
    coalesce(prev.overdue_amount, 0) AS overdue_amount_prev,
    curr.overdue_amount - coalesce(prev.overdue_amount, 0) AS overdue_delta,
    curr.overdue_rate AS overdue_rate_curr,
    coalesce(prev.overdue_rate, 0) AS overdue_rate_prev,
    curr.total_ar_amount AS total_ar_curr,
    curr.overdue_count AS overdue_count_curr
FROM dm.dm_customer_ar curr
LEFT JOIN dm.dm_customer_ar prev
    ON curr.customer_code = prev.customer_code
    AND curr.company_code = prev.company_code
    AND prev.stat_date = toDate({prev_date})
WHERE curr.stat_date = toDate({current_date})
ORDER BY overdue_delta DESC
LIMIT 10
""",
    "time": """
SELECT
    stat_date,
    overdue_amount,
    total_ar_amount,
    overdue_rate,
    lagInFrame(overdue_rate) OVER (ORDER BY stat_date) AS prev_overdue_rate,
    overdue_rate - lagInFrame(overdue_rate) OVER (ORDER BY stat_date) AS rate_delta
FROM dm.dm_ar_summary
WHERE stat_date BETWEEN {start_date} AND {end_date}
  AND company_code = {company_code}
ORDER BY stat_date
""",
}


class AttributionService:
    """归因分析服务"""

    def __init__(
        self,
        ollama_service: OllamaService | None = None,
        clickhouse_service: ClickHouseDataService | None = None,
    ):
        self.ollama = ollama_service or OllamaService()
        self.clickhouse = clickhouse_service or ClickHouseDataService()

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """从 LLM 输出中提取 JSON"""
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def analyze(self, question: str) -> AttributionResult:
        """
        执行归因分析

        Args:
            question: 用户问题，如 "为什么本月逾期率上升了"

        Returns:
            AttributionResult
        """
        start_time = time.time()

        # Step 1: 调用 LLM 生成假设
        try:
            response = self.ollama.generate(
                prompt=question,
                system=ATTRIBUTION_SYSTEM_PROMPT,
            )
        except Exception as e:
            return AttributionResult(
                question=question,
                factors=[],
                overall_confidence=0.0,
                analysis_time=time.time() - start_time,
                raw_data={"error": str(e)},
            )

        hypotheses_data = self._extract_json(response)
        hypotheses = []
        if hypotheses_data:
            hypotheses = hypotheses_data.get("hypotheses", [])

        # Step 2: 并行验证每个假设（只执行 customer 和 time）
        raw_data: dict[str, Any] = {}
        for hypo in hypotheses:
            dimension = hypo.get("dimension", "")
            if dimension not in ("customer", "time"):
                continue

            sql = SQL_TEMPLATES.get(dimension, "")
            if not sql:
                continue

            # 填充日期参数（简化：使用最近两个统计日期）
            try:
                dates_result = self.clickhouse.execute_query(
                    "SELECT DISTINCT stat_date FROM dm.dm_ar_summary ORDER BY stat_date DESC LIMIT 2"
                )
                if len(dates_result) >= 2:
                    current_date = str(dates_result[0].get("stat_date", ""))
                    prev_date = str(dates_result[1].get("stat_date", ""))
                else:
                    logger.warning("Insufficient date data in dm_ar_summary, using fallback dates")
                    current_date = "2023-10-31"
                    prev_date = "2023-09-30"
            except Exception as e:
                logger.warning(f"Failed to query dates, using fallback dates: {e}")
                current_date = "2023-10-31"
                prev_date = "2023-09-30"

            sql_params = {
                "current_date": current_date,
                "prev_date": prev_date,
                "start_date": prev_date,
                "end_date": current_date,
                "company_code": "C001",
            }

            try:
                sql_result = self.clickhouse.execute_query(sql, sql_params)
                raw_data[dimension] = {
                    "sql": sql,  # Don't leak interpolated SQL; template is safe to show
                    "result": sql_result,
                    "confidence": calc_confidence(sql_result, dimension),
                }
            except Exception as e:
                raw_data[dimension] = {"error": str(e), "sql": sql}

        # Step 3: 生成归因因子
        factors: list[Factor] = []
        for hypo in hypotheses:
            dimension = hypo.get("dimension", "")
            if dimension not in raw_data:
                continue
            dim_data = raw_data[dimension]
            if "error" in dim_data:
                continue

            factors.append(
                Factor(
                    dimension=dimension,
                    description=hypo.get("description", ""),
                    contribution=0.5,
                    evidence=dim_data.get("result", {}),
                    confidence=dim_data.get("confidence", 0.0),
                    suggestion=hypo.get("reasoning", ""),
                )
            )

        # 按置信度排序，取 Top 3
        factors.sort(key=lambda f: f.confidence, reverse=True)
        factors = factors[:3]

        overall_confidence = (
            sum(f.confidence for f in factors) / len(factors) if factors else 0.0
        )

        return AttributionResult(
            question=question,
            factors=factors,
            overall_confidence=overall_confidence,
            analysis_time=time.time() - start_time,
            raw_data=raw_data,
        )
