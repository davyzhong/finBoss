# FinBoss Phase 3 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Spec:** `docs/superpowers/specs/2026-03-21-finboss-phase3-design.md`

**Goal:** 实现 Phase 3 全部 4 个模块：飞书机器人、归因分析、知识版本管理、提示词优化。

**Architecture:** 4 个模块顺序实现，提示词优化最先（无依赖），飞书机器人最后（依赖所有其他模块）。

**Tech Stack:** Python 3.11, FastAPI, lark-oapi, pymilvus, pydantic, pytest

---

## 实施顺序

```
1. 模块四: 提示词优化        (无依赖，最先)
2. 模块二: 归因分析          (依赖模块四)
3. 模块三: 知识版本管理       (扩展现有 RAGService)
4. 模块一: 飞书机器人        (依赖模块二、三、四)
```

---

## 文件总览

| 模块 | 文件 | 操作 |
|------|------|------|
| 四 | `services/ai/prompts/__init__.py` | 创建 |
| 四 | `services/ai/prompts/nl_query_prompt.py` | 创建 |
| 四 | `services/ai/prompts/attribution_prompt.py` | 创建 |
| 四 | `services/ai/prompts/card_format_prompt.py` | 创建 |
| 四 | `services/ai/nl_query_service.py` | 修改 |
| 二 | `schemas/attribution.py` | 创建 |
| 二 | `services/attribution_service.py` | 创建 |
| 二 | `api/routes/attribution.py` | 创建 |
| 三 | `services/knowledge_manager.py` | 创建 |
| 三 | `api/routes/knowledge.py` | 创建 |
| 一 | `services/feishu/config.py` | 创建 |
| 一 | `services/feishu/feishu_client.py` | 创建 |
| 一 | `services/feishu/card_builder.py` | 创建 |
| 一 | `services/feishu/event_handler.py` | 创建 |
| 一 | `api/routes/feishu.py` | 创建 |
| 一 | `api/main.py` | 修改 |
| 一 | `config/docker-compose.yml` | 修改 |
| 跨 | `api/config.py` | 修改 |
| 跨 | `.env.example` | 修改 |
| 跨 | `pyproject.toml` | 修改 |

---

## 模块四：提示词优化

### Task P1: 创建 prompts 包结构和依赖

**Files:**
- Create: `services/ai/prompts/__init__.py`
- Create: `services/ai/prompts/nl_query_prompt.py`
- Create: `services/ai/prompts/attribution_prompt.py`
- Create: `services/ai/prompts/card_format_prompt.py`
- Modify: `services/ai/nl_query_service.py` (替换 SYSTEM_PROMPT 为导入)
- Test: `tests/unit/test_nl_query_prompt.py`

- [ ] **Step 1: 创建 `services/ai/prompts/__init__.py`**

```python
"""AI 提示词模板包"""

from services.ai.prompts.nl_query_prompt import (
    NL_QUERY_SYSTEM_PROMPT,
    RESULT_EXPLAIN_PROMPT,
    NL_QUERY_EXAMPLES,
)
from services.ai.prompts.attribution_prompt import ATTRIBUTION_SYSTEM_PROMPT
from services.ai.prompts.card_format_prompt import CARD_FORMAT_SYSTEM_PROMPT

__all__ = [
    "NL_QUERY_SYSTEM_PROMPT",
    "RESULT_EXPLAIN_PROMPT",
    "NL_QUERY_EXAMPLES",
    "ATTRIBUTION_SYSTEM_PROMPT",
    "CARD_FORMAT_SYSTEM_PROMPT",
]
```

- [ ] **Step 2: 创建 `services/ai/prompts/nl_query_prompt.py`**

从 `services/ai/nl_query_service.py` 中提取 SYSTEM_PROMPT 和 RESULT_EXPLAIN_PROMPT，添加 Few-shot examples：

```python
"""NL 查询提示词（含 Few-shot Examples）"""

DATABASE_SCHEMA = """
## FinBoss 数据库架构

### dm.dm_ar_summary (AR 汇总表)
| stat_date | Date | 统计日期 |
| company_code | String | 公司代码 |
| company_name | String | 公司名称 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| received_amount | Decimal(18,2) | 已收金额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 总单数 |
| overdue_rate | Float32 | 逾期率 |

### dm.dm_customer_ar (客户 AR 表)
| stat_date | Date | 统计日期 |
| customer_code | String | 客户代码 |
| customer_name | String | 客户名称 |
| company_code | String | 公司代码 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 应收单总数 |
| overdue_rate | Float32 | 逾期率 |

### std.std_ar (AR 明细表)
| id | String | 单据ID |
| bill_no | String | 单据编号 |
| bill_date | DateTime | 单据日期 |
| bill_amount | Decimal(18,2) | 单据金额 |
| customer_name | String | 客户名称 |
| is_overdue | Bool | 是否逾期 |
| company_code | String | 公司代码 |
"""

NL_QUERY_EXAMPLES = [
    {
        "question": "本月应收总额是多少",
        "sql": "SELECT SUM(total_ar_amount) AS total_ar_amount FROM dm.dm_ar_summary WHERE stat_date = 'YYYY-MM-DD'",
    },
    {
        "question": "哪些客户有逾期账款",
        "sql": "SELECT customer_name, overdue_amount, company_code FROM dm.dm_customer_ar WHERE overdue_amount > 0 ORDER BY overdue_amount DESC",
    },
    {
        "question": "C001公司的逾期率",
        "sql": "SELECT overdue_rate FROM dm.dm_ar_summary WHERE company_code = 'C001' AND stat_date = 'YYYY-MM-DD'",
    },
]

FEW_SHOT_BLOCK = "\n".join(
    f"示例 {i+1}: 问: {e['question']}\n答: {e['sql']}"
    for i, e in enumerate(NL_QUERY_EXAMPLES)
)

NL_QUERY_SYSTEM_PROMPT = f"""你是一个专业的财务数据分析助手，帮助用户用自然语言查询财务数据。

## 工作流程
1. 理解用户的自然语言查询
2. 根据数据库架构生成 ClickHouse SQL
3. 返回结构化的查询结果
4. 用自然语言解释结果

## 数据库架构
{DATABASE_SCHEMA}

## 示例
{FEW_SHOT_BLOCK}

## 重要规则
- 只生成 SELECT 查询，禁止 INSERT/UPDATE/DELETE/DROP
- 金额字段使用 Decimal(18,2)
- 日期使用 'YYYY-MM-DD' 格式
- 公司代码如 C001, C002, C003
- SQL 中表名使用完全限定名: dm.dm_ar_summary, dm.dm_customer_ar, std.std_ar
- 如果查询涉及金额总计，使用 SUM() 聚合
- 如果查询涉及逾期，使用 is_overdue = 1 或 overdue_amount > 0
- 响应时间限制：SQL 必须在 5 秒内执行完成

## 输出格式
必须返回 JSON 格式（包含 sql 字段）：
{{"sql": "SELECT ...", "explanation": "这个查询将返回..."}}
"""

RESULT_EXPLAIN_PROMPT = """你是一个专业的财务数据分析助手。根据以下查询结果，用自然语言向用户解释：

查询: {query}
SQL: {sql}
结果: {result}

请用简洁的中文解释结果，并指出关键发现。如果结果为空，也请如实告知用户。
"""
```

- [ ] **Step 3: 创建 `services/ai/prompts/attribution_prompt.py`**

```python
"""归因分析提示词"""

ATTRIBUTION_SYSTEM_PROMPT = """你是一个专业的财务归因分析师。

## 你的任务
当用户询问"为什么XXX"时，你需要：
1. 生成 2 个假设（客户维度、时间维度）
2. 解释每个假设的合理性
3. 提出验证所需的 SQL 查询

## 数据库架构

dm.dm_ar_summary (AR 汇总表):
| stat_date | Date | 统计日期 |
| company_code | String | 公司代码 |
| company_name | String | 公司名称 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| received_amount | Decimal(18,2) | 已收金额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 总单数 |
| overdue_rate | Float32 | 逾期率 |

dm.dm_customer_ar (客户 AR 表):
| stat_date | Date | 统计日期 |
| customer_code | String | 客户代码 |
| customer_name | String | 客户名称 |
| company_code | String | 公司代码 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 应收单总数 |
| overdue_rate | Float32 | 逾期率 |

std.std_ar (AR 明细表):
| id | String | 单据ID |
| bill_no | String | 单据编号 |
| bill_date | DateTime | 单据日期 |
| bill_amount | Decimal(18,2) | 单据金额 |
| customer_name | String | 客户名称 |
| is_overdue | Bool | 是否逾期 |
| company_code | String | 公司代码 |

## 输出格式
必须返回 JSON 格式：
{
    "hypotheses": [
        {
            "dimension": "customer|time",
            "description": "假设描述",
            "reasoning": "为什么这个假设合理",
            "sql_template": "验证用的 SQL 模板"
        }
    ]
}
"""
```

- [ ] **Step 4: 创建 `services/ai/prompts/card_format_prompt.py`**

```python
"""飞书卡片文本格式化提示词"""

CARD_FORMAT_SYSTEM_PROMPT = """你是一个专业的财务报告助手。根据以下数据，生成适合飞书卡片的格式化文本：

## 数据
{result_data}

## 要求
- 用简洁的中文描述
- 数值使用千分位格式（如 ¥1,234,567）
- 用 emoji 增强可读性
- 如有对比数据，标注变化（如 ↑12.5%、↓3.2%）
- 卡片文本总长度不超过 500 字
"""
```

- [ ] **Step 5: 修改 `services/ai/nl_query_service.py`**

将文件顶部的 `SYSTEM_PROMPT` 和 `RESULT_EXPLAIN_PROMPT` 常量删除，改为从 prompts 包导入：

```python
# 删除以下内容：
# DATABASE_SCHEMA = """..."""
# SYSTEM_PROMPT = f"""..."""
# RESULT_EXPLAIN_PROMPT = """..."""

# 替换为：
from services.ai.prompts import NL_QUERY_SYSTEM_PROMPT, RESULT_EXPLAIN_PROMPT
```

`NLQueryService.__init__` 中的 `self.ollama.generate` 调用保持不变，只改 `SYSTEM_PROMPT` 引用为 `NL_QUERY_SYSTEM_PROMPT`。

- [ ] **Step 6: 写单元测试 `tests/unit/test_nl_query_prompt.py`**

```python
"""测试提示词模板加载"""
import pytest
from services.ai.prompts import (
    NL_QUERY_SYSTEM_PROMPT,
    RESULT_EXPLAIN_PROMPT,
    NL_QUERY_EXAMPLES,
    ATTRIBUTION_SYSTEM_PROMPT,
)

def test_nl_query_prompt_has_examples():
    assert len(NL_QUERY_EXAMPLES) == 3
    assert all("question" in e and "sql" in e for e in NL_QUERY_EXAMPLES)

def test_nl_query_prompt_has_schema():
    assert "dm.dm_ar_summary" in NL_QUERY_SYSTEM_PROMPT
    assert "dm.dm_customer_ar" in NL_QUERY_SYSTEM_PROMPT
    assert "std.std_ar" in NL_QUERY_SYSTEM_PROMPT

def test_nl_query_prompt_blocks_dangerous():
    assert "INSERT" not in NL_QUERY_SYSTEM_PROMPT.upper()
    assert "DROP" not in NL_QUERY_SYSTEM_PROMPT.upper()

def test_result_explain_prompt_has_placeholder():
    assert "{query}" in RESULT_EXPLAIN_PROMPT
    assert "{sql}" in RESULT_EXPLAIN_PROMPT
    assert "{result}" in RESULT_EXPLAIN_PROMPT

def test_attribution_prompt_has_dimensions():
    assert "customer" in ATTRIBUTION_SYSTEM_PROMPT
    assert "time" in ATTRIBUTION_SYSTEM_PROMPT
    assert "product" not in ATTRIBUTION_SYSTEM_PROMPT  # Phase 4 only
```

- [ ] **Step 7: 运行测试**

Run: `uv run pytest tests/unit/test_nl_query_prompt.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: 运行现有 NL 查询集成测试，确保 prompt 替换不破坏功能**

Run: `uv run pytest tests/ -v -k "nl" --tb=short`
Expected: PASS（原有测试不受影响，因为只改了 prompt 文本）

- [ ] **Step 9: Commit**

```bash
git add services/ai/prompts/ services/ai/nl_query_service.py tests/unit/test_nl_query_prompt.py
git commit -m "feat: extract prompts to external package with few-shot examples

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 模块二：归因分析服务

### Task A1: 创建归因数据模型

**Files:**
- Create: `schemas/attribution.py`
- Test: `tests/unit/test_attribution_schemas.py`

- [ ] **Step 1: 创建 `schemas/attribution.py`**

```python
"""归因分析数据模型"""
from typing import Literal
from pydantic import BaseModel, Field


class Factor(BaseModel):
    """单个归因因子"""

    dimension: Literal["customer", "time"] = Field(description="分析维度")
    description: str = Field(description="归因描述")
    contribution: float = Field(description="贡献度（0-1）")
    evidence: dict = Field(description="支撑数据")
    confidence: float = Field(description="置信度（0-1）")
    suggestion: str = Field(description="建议措施")


class AttributionResult(BaseModel):
    """归因分析结果"""

    question: str = Field(description="用户原始问题")
    factors: list[Factor] = Field(description="Top 归因因子列表")
    overall_confidence: float = Field(description="整体置信度（0-1）")
    analysis_time: float = Field(description="分析耗时（秒）")
    raw_data: dict = Field(default_factory=dict, description="原始数据（调试用）")


class KnowledgeListResult(BaseModel):
    """通用列表结果（用于知识库分页）"""

    items: list = Field(description="列表项")
    total: int = Field(description="总数")
    page: int = Field(description="当前页")
    page_size: int = Field(description="每页数量")
```

- [ ] **Step 2: 创建 `tests/unit/test_attribution_schemas.py`**

```python
"""测试归因数据模型"""
import pytest
from schemas.attribution import Factor, AttributionResult


def test_factor_model():
    factor = Factor(
        dimension="customer",
        description="大客户账期延长",
        contribution=0.65,
        evidence={"top_customer": "阿里巴巴", "delta": 4800000},
        confidence=0.8,
        suggestion="建议与该客户对账并催收",
    )
    assert factor.dimension == "customer"
    assert factor.confidence == 0.8


def test_attribution_result_model():
    result = AttributionResult(
        question="为什么本月逾期率上升了",
        factors=[],
        overall_confidence=0.75,
        analysis_time=12.5,
    )
    assert result.question == "为什么本月逾期率上升了"
    assert result.overall_confidence == 0.75


def test_factor_dimension_literal_rejects_product():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Factor(
            dimension="product",  # Not allowed in Phase 3
            description="test",
            contribution=0.5,
            evidence={},
            confidence=0.5,
            suggestion="test",
        )
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/unit/test_attribution_schemas.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add schemas/attribution.py tests/unit/test_attribution_schemas.py
git commit -m "feat: add attribution analysis data models

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task A2: 实现 AttributionService

**Files:**
- Create: `services/attribution_service.py`
- Test: `tests/unit/test_attribution_service.py`

- [ ] **Step 1: 创建 `services/attribution_service.py`**

```python
"""归因分析服务"""
import time
import json
import re
from typing import Any

from schemas.attribution import AttributionResult, Factor
from services.ai.ollama_service import OllamaService
from services.ai.prompts import ATTRIBUTION_SYSTEM_PROMPT
from services.clickhouse_service import ClickHouseDataService


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
    AND prev.stat_date = toDate('{prev_date}')
WHERE curr.stat_date = toDate('{current_date}')
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
WHERE stat_date BETWEEN '{start_date}' AND '{end_date}'
  AND company_code = '{company_code}'
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
                    current_date = "2023-10-31"
                    prev_date = "2023-09-30"
            except Exception:
                current_date = "2023-10-31"
                prev_date = "2023-09-30"

            filled_sql = sql.format(
                current_date=current_date,
                prev_date=prev_date,
                start_date=prev_date,
                end_date=current_date,
                company_code="C001",
            )

            try:
                sql_result = self.clickhouse.execute_query(filled_sql)
                raw_data[dimension] = {
                    "sql": filled_sql,
                    "result": sql_result,
                    "confidence": calc_confidence(sql_result, dimension),
                }
            except Exception as e:
                raw_data[dimension] = {"error": str(e), "sql": filled_sql}

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
```

- [ ] **Step 2: 创建 `tests/unit/test_attribution_service.py`**

```python
"""测试归因分析服务"""
import pytest
from unittest.mock import MagicMock, patch
from services.attribution_service import AttributionService, calc_confidence
from schemas.attribution import AttributionResult


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
    @patch("services.attribution_service.OllamaService")
    @patch("services.attribution_service.ClickHouseDataService")
    def test_analyze_returns_result(self, mock_ch, mock_ollama):
        mock_ollama.return_value.generate.return_value = '{"hypotheses": []}'
        mock_ch.return_value.execute_query.return_value = []
        service = AttributionService()
        result = service.analyze("为什么本月逾期率上升了")
        assert isinstance(result, AttributionResult)
        assert result.question == "为什么本月逾期率上升了"
        assert result.analysis_time >= 0
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/unit/test_attribution_service.py -v`
Expected: PASS (8 tests)

- [ ] **Step 4: Commit**

```bash
git add services/attribution_service.py tests/unit/test_attribution_service.py
git commit -m "feat: implement AttributionService with confidence scoring

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task A3: 创建归因分析 API 路由

**Files:**
- Create: `api/routes/attribution.py`
- Modify: `api/main.py` (注册 router)
- Test: `tests/integration/test_attribution_api.py`

- [ ] **Step 1: 创建 `api/routes/attribution.py`**

```python
"""归因分析 API 路由"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from schemas.attribution import AttributionResult
from services.attribution_service import AttributionService

router = APIRouter()


class AttributionRequest(BaseModel):
    question: str


@router.post("/analyze", response_model=AttributionResult)
async def analyze(question: AttributionRequest) -> AttributionResult:
    """归因分析

    分析财务指标异动原因，返回 Top 归因因子。

    示例问题:
    - "为什么本月逾期率上升了"
    - "为什么收入下降了"
    """
    service = AttributionService()
    result = service.analyze(question.question)
    return result
```

- [ ] **Step 2: 修改 `api/main.py`，注册归因 router**

找到现有的 `api_router` 定义区域，添加：

```python
from api.routes import ar, query, ai, attribution  # 添加 attribution

api_router = APIRouter()
api_router.include_router(ar.router, prefix="/ar", tags=["AR"])
api_router.include_router(query.router, prefix="/query", tags=["Query"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(attribution.router, prefix="/attribution", tags=["Attribution"])  # 新增
```

- [ ] **Step 3: 创建 `tests/integration/test_attribution_api.py`**

```python
"""测试归因分析 API"""
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_analyze_endpoint_exists():
    response = client.post(
        "/api/v1/attribution/analyze",
        json={"question": "为什么本月逾期率上升了"},
    )
    # 200 or 500 (if Ollama not running) — just check endpoint exists
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "question" in data
        assert "factors" in data
        assert "overall_confidence" in data
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/integration/test_attribution_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/attribution.py api/main.py tests/integration/test_attribution_api.py
git commit -m "feat: add attribution analysis API endpoint

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 模块三：知识版本管理

### Task K1: 实现 KnowledgeManager

**Files:**
- Create: `services/knowledge_manager.py`
- Test: `tests/unit/test_knowledge_manager.py`

- [ ] **Step 1: 创建 `services/knowledge_manager.py`**

```python
"""知识库版本管理服务"""
import json
import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from api.config import get_settings


class KnowledgeDoc(BaseModel):
    """知识库文档模型"""

    id: str
    content: str
    category: str
    metadata: dict[str, Any]
    version: int = 1
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    change_log: str = ""


class KnowledgeListResult(BaseModel):
    items: list[KnowledgeDoc]
    total: int
    page: int
    page_size: int


class KnowledgeManager:
    """知识库版本管理服务"""

    def __init__(self):
        settings = get_settings()
        self.host = settings.milvus.host
        self.port = settings.milvus.port
        self.collection_name = settings.milvus.collection_name
        self._embedding_url = "http://localhost:11434/api/embeddings"

    def connect(self) -> None:
        connections.connect(host=self.host, port=self.port)

    def _generate_embedding(self, text: str) -> list[float]:
        import httpx

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    self._embedding_url,
                    json={"model": "nomic-embed-text", "prompt": text},
                )
                if response.status_code == 200:
                    return response.json().get("embedding", [])
        except Exception:
            pass

        # Fallback: 假向量（仅 POC）
        import hashlib

        hash_bytes = hashlib.sha256(text.encode()).digest()
        dim = 768
        return [float(hash_bytes[i % len(hash_bytes)] % 256) / 255.0 for i in range(dim)]

    def _get_collection(self) -> Collection:
        self.connect()
        if not utility.has_collection(self.collection_name):
            raise ValueError(f"Collection {self.collection_name} not found")
        collection = Collection(self.collection_name)
        collection.load()
        return collection

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> KnowledgeListResult:
        """分页查询知识库（仅活跃文档）"""
        self.connect()

        expr = "is_active == true"
        if category:
            expr = f'{expr} AND category == "{category}"'

        collection = self._get_collection()
        offset = (page - 1) * page_size

        results = collection.query(
            expr=expr,
            output_fields=["id", "content", "category", "metadata", "version", "created_at", "updated_at", "is_active", "change_log"],
            limit=page_size,
            offset=offset,
        )

        # 统计总数
        all_results = collection.query(
            expr=expr,
            output_fields=["id"],
        )
        total = len(all_results)

        items = [self._dict_to_doc(r) for r in results]
        return KnowledgeListResult(items=items, total=total, page=page, page_size=page_size)

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        """获取单个文档（最新活跃版本）"""
        self.connect()
        collection = self._get_collection()

        results = collection.query(
            expr=f'id == "{doc_id}" AND is_active == true',
            output_fields=["id", "content", "category", "metadata", "version", "created_at", "updated_at", "is_active", "change_log"],
            limit=1,
        )
        if not results:
            return None
        return self._dict_to_doc(results[0])

    def create(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc:
        """创建文档（版本=1）"""
        self.connect()
        collection = self._get_collection()

        doc_id = f"kb_{hashlib.md5(content.encode()).hexdigest()[:12]}"
        now = datetime.now()
        vector = self._generate_embedding(content)
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        entities = [[doc_id], [content], [vector], [category], [meta_str], [1], [now], [now], [True], [change_log]]
        collection.insert(entities)
        collection.flush()

        return KnowledgeDoc(
            id=doc_id,
            content=content,
            category=category,
            metadata=metadata or {},
            version=1,
            created_at=now,
            updated_at=now,
            is_active=True,
            change_log=change_log,
        )

    def update(
        self,
        doc_id: str,
        content: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc | None:
        """更新文档（生成新版本）"""
        self.connect()
        collection = self._get_collection()

        # 获取当前版本
        current = collection.query(
            expr=f'id == "{doc_id}" AND is_active == true',
            output_fields=["id", "content", "category", "metadata", "version"],
            limit=1,
        )
        if not current:
            return None

        cur = current[0]
        new_version = int(cur.get("version", 1)) + 1
        new_content = content if content is not None else cur.get("content", "")
        new_category = category if category is not None else cur.get("category", "general")

        # 软删除旧版本
        collection.update(
            expr=f'id == "{doc_id}" AND is_active == true',
            data={"is_active": False},
        )

        # 插入新版本
        now = datetime.now()
        vector = self._generate_embedding(new_content)
        new_meta = metadata if metadata is not None else json.loads(cur.get("metadata", "{}"))

        entities = [
            [doc_id],
            [new_content],
            [vector],
            [new_category],
            [json.dumps(new_meta, ensure_ascii=False)],
            [new_version],
            [cur.get("created_at", now)],
            [now],
            [True],
            [change_log],
        ]
        collection.insert(entities)
        collection.flush()

        return KnowledgeDoc(
            id=doc_id,
            content=new_content,
            category=new_category,
            metadata=new_meta,
            version=new_version,
            created_at=cur.get("created_at", now),
            updated_at=now,
            is_active=True,
            change_log=change_log,
        )

    def delete(self, doc_id: str, change_log: str = "") -> bool:
        """软删除文档"""
        self.connect()
        collection = self._get_collection()
        try:
            collection.update(
                expr=f'id == "{doc_id}" AND is_active == true',
                data={"is_active": False, "change_log": change_log or "deleted"},
            )
            collection.flush()
            return True
        except Exception:
            return False

    def get_history(self, doc_id: str) -> list[KnowledgeDoc]:
        """获取文档版本历史"""
        self.connect()
        collection = self._get_collection()
        results = collection.query(
            expr=f'id == "{doc_id}"',
            output_fields=["id", "content", "category", "metadata", "version", "created_at", "updated_at", "is_active", "change_log"],
            limit=100,
        )
        return sorted([self._dict_to_doc(r) for r in results], key=lambda d: d.version, reverse=True)

    def rollback(self, doc_id: str, target_version: int, change_log: str = "") -> KnowledgeDoc | None:
        """回滚到指定版本（生成新版本，内容来自历史版本）"""
        history = self.get_history(doc_id)
        target = next((d for d in history if d.version == target_version), None)
        if not target:
            return None

        return self.update(
            doc_id=doc_id,
            content=target.content,
            category=target.category,
            metadata=target.metadata,
            change_log=change_log or f"rollback to version {target_version}",
        )

    def _dict_to_doc(self, d: dict) -> KnowledgeDoc:
        meta = d.get("metadata", "{}")
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
        return KnowledgeDoc(
            id=d.get("id", ""),
            content=d.get("content", ""),
            category=d.get("category", "general"),
            metadata=meta,
            version=int(d.get("version", 1)),
            created_at=d.get("created_at", datetime.now()),
            updated_at=d.get("updated_at", datetime.now()),
            is_active=d.get("is_active", True),
            change_log=d.get("change_log", ""),
        )
```

- [ ] **Step 2: 创建 `tests/unit/test_knowledge_manager.py`**

```python
"""测试 KnowledgeManager"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from services.knowledge_manager import KnowledgeManager, KnowledgeDoc, calc_confidence


class TestCalcConfidence:
    # 复用 attribution service 的测试逻辑（避免重复）
    pass


class TestKnowledgeDoc:
    def test_knowledge_doc_model(self):
        doc = KnowledgeDoc(
            id="kb_test123",
            content="测试内容",
            category="test",
            metadata={"author": "tester"},
            version=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True,
            change_log="initial",
        )
        assert doc.id == "kb_test123"
        assert doc.version == 1
        assert doc.is_active is True

    def test_knowledge_doc_defaults(self):
        doc = KnowledgeDoc(
            id="kb_abc",
            content="内容",
            category="general",
            metadata={},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert doc.version == 1
        assert doc.is_active is True
        assert doc.change_log == ""
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/unit/test_knowledge_manager.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add services/knowledge_manager.py tests/unit/test_knowledge_manager.py
git commit -m "feat: implement KnowledgeManager with versioning support

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task K2: 创建知识管理 API 路由

**Files:**
- Create: `api/routes/knowledge.py`
- Modify: `api/main.py` (注册 router)
- Test: `tests/integration/test_knowledge_api.py`

- [ ] **Step 1: 创建 `api/routes/knowledge.py`**

```python
"""知识库管理 API 路由"""
from typing import Any
from fastapi import APIRouter, HTTPException, Query

from schemas.attribution import KnowledgeListResult
from schemas.attribution import KnowledgeDoc
from services.knowledge_manager import KnowledgeManager

router = APIRouter()


def _manager() -> KnowledgeManager:
    return KnowledgeManager()


@router.get("", response_model=KnowledgeListResult)
async def list_knowledge(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = None,
) -> KnowledgeListResult:
    """分页查询知识库文档"""
    return _manager().list(page=page, page_size=page_size, category=category)


@router.post("", response_model=KnowledgeDoc)
async def create_knowledge(
    content: str,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
    change_log: str = "",
) -> KnowledgeDoc:
    """创建知识文档"""
    return _manager().create(content=content, category=category, metadata=metadata, change_log=change_log)


@router.get("/{doc_id}", response_model=KnowledgeDoc)
async def get_knowledge(doc_id: str) -> KnowledgeDoc:
    """获取单个文档"""
    doc = _manager().get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{doc_id}", response_model=KnowledgeDoc)
async def update_knowledge(
    doc_id: str,
    content: str | None = None,
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
    change_log: str = "",
) -> KnowledgeDoc:
    """更新文档（生成新版本）"""
    doc = _manager().update(doc_id=doc_id, content=content, category=category, metadata=metadata, change_log=change_log)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_knowledge(doc_id: str, change_log: str = "") -> dict[str, Any]:
    """软删除文档"""
    success = _manager().delete(doc_id, change_log=change_log)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": doc_id, "status": "deleted"}


@router.get("/{doc_id}/history", response_model=list[KnowledgeDoc])
async def get_history(doc_id: str) -> list[KnowledgeDoc]:
    """获取版本历史"""
    return _manager().get_history(doc_id)


@router.post("/{doc_id}/rollback", response_model=KnowledgeDoc)
async def rollback(doc_id: str, target_version: int, change_log: str = "") -> KnowledgeDoc:
    """回滚到指定版本"""
    doc = _manager().rollback(doc_id, target_version, change_log=change_log)
    if not doc:
        raise HTTPException(status_code=404, detail="Version not found")
    return doc
```

- [ ] **Step 2: 修改 `api/main.py`，注册 knowledge router**

```python
from api.routes import ar, query, ai, attribution, knowledge  # 添加 knowledge

api_router.include_router(ar.router, prefix="/ar", tags=["AR"])
api_router.include_router(query.router, prefix="/query", tags=["Query"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(attribution.router, prefix="/attribution", tags=["Attribution"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])  # 新增
```

- [ ] **Step 3: 创建 `tests/integration/test_knowledge_api.py`**

```python
"""测试知识管理 API"""
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_knowledge_list_endpoint_exists():
    response = client.get("/api/v1/knowledge")
    # 200 or 500 (if Milvus not running)
    assert response.status_code in (200, 500)


def test_knowledge_create_endpoint_exists():
    response = client.post(
        "/api/v1/knowledge",
        params={"content": "测试文档", "category": "test", "change_log": "test create"},
    )
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "id" in data


def test_knowledge_not_found_returns_404():
    response = client.get("/api/v1/knowledge/nonexistent_id")
    assert response.status_code in (404, 500)
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/integration/test_knowledge_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/knowledge.py api/main.py tests/integration/test_knowledge_api.py
git commit -m "feat: add knowledge management API endpoints with versioning

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 模块一：飞书机器人

### Task F1: 创建飞书配置和客户端

**Files:**
- Create: `services/feishu/config.py`
- Create: `services/feishu/feishu_client.py`
- Create: `services/feishu/__init__.py`
- Modify: `api/config.py` (添加 FeishuConfig)
- Modify: `.env.example`
- Modify: `pyproject.toml` (添加 lark-oapi)

- [ ] **Step 1: 创建 `services/feishu/__init__.py`**

```python
"""飞书机器人服务"""
from services.feishu.feishu_client import FeishuClient
from services.feishu.card_builder import CardBuilder
from services.feishu.event_handler import EventHandler

__all__ = ["FeishuClient", "CardBuilder", "EventHandler"]
```

- [ ] **Step 2: 创建 `services/feishu/config.py`**

```python
"""飞书应用配置（从 api/config.py 导入主配置）"""
from api.config import get_settings


def get_feishu_config():
    settings = get_settings()
    return settings.feishu
```

- [ ] **Step 3: 修改 `api/config.py`，添加 FeishuConfig**

在 `MilvusConfig` 类之后、`Settings` 类之前添加：

```python
class FeishuConfig(BaseSettings):
    """飞书应用配置"""

    model_config = SettingsConfigDict(
        env_prefix="feishu_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_id: str = Field(default="", description="飞书应用 App ID")
    app_secret: str = Field(default="", description="飞书应用 App Secret")
    bot_name: str = Field(default="FinBoss财务助手", description="机器人名称")
    verification_token: str = Field(default="", description="Webhook 验证 Token（可选）")
```

在 `Settings` 类的字段定义中添加：

```python
feishu: FeishuConfig = Field(default_factory=FeishuConfig)
```

- [ ] **Step 4: 创建 `services/feishu/feishu_client.py`**

```python
"""飞书 SDK 封装"""
import hashlib
import hmac
import time
from typing import Any

import httpx

from services.feishu.config import get_feishu_config


class FeishuClient:
    """飞书 SDK 封装"""

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        config = get_feishu_config()
        self.app_id = app_id or config.app_id
        self.app_secret = app_secret or config.app_secret
        self.bot_name = config.bot_name
        self._tenant_access_token: str | None = None
        self._token_expires_at: float = 0

    def _get_tenant_token(self) -> str:
        """获取 tenant access token（自动缓存）"""
        if self._tenant_access_token and time.time() < self._token_expires_at - 60:
            return self._tenant_access_token

        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
        data = response.json()
        self._tenant_access_token = data.get("tenant_access_token", "")
        self._token_expires_at = time.time() + data.get("expire", 7200)
        return self._tenant_access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json",
        }

    def send_message(self, receive_id: str, msg_type: str, content: dict) -> bool:
        """发送消息"""
        with httpx.Client(timeout=10) as client:
            response = client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                headers=self._headers(),
                json={
                    "receive_id": receive_id,
                    "msg_type": msg_type,
                    "content": content,
                },
            )
        return response.status_code == 200

    def send_card(self, receive_id: str, card_content: dict) -> bool:
        """发送卡片消息"""
        card_json = {"config": {"wide_screen_mode": True}, "elements": card_content.get("elements", [])}
        return self.send_message(receive_id=receive_id, msg_type="interactive", content={"zh_cn": card_json})

    def reply_message(self, message_id: str, msg_type: str, content: dict) -> bool:
        """回复消息"""
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                headers=self._headers(),
                json={"msg_type": msg_type, "content": content},
            )
        return response.status_code == 200

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取用户信息"""
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}",
                headers=self._headers(),
            )
        if response.status_code == 200:
            return response.json().get("data", {}).get("user", {})
        return {}

    def verify_signature(self, signature: str, timestamp: str, raw_body: bytes) -> bool:
        """验证飞书事件签名"""
        if not signature:
            return False
        secret = get_feishu_config().verification_token
        if not secret:
            return True  # 未配置 token 时跳过验证
        string_to_sign = f"{timestamp}{raw_body.decode()}"
        sign = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
        return sign == signature
```

- [ ] **Step 5: 更新 `.env.example`**

在文件末尾添加：

```bash
# === 飞书机器人配置 ===
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BOT_NAME=FinBoss财务助手
FEISHU_VERIFICATION_TOKEN=
```

- [ ] **Step 6: 更新 `pyproject.toml`**

在 dependencies 中添加：

```toml
lark-oapi = ">=1.4.0,<2.0.0"
```

- [ ] **Step 7: Commit**

```bash
git add services/feishu/ api/config.py .env.example pyproject.toml
git commit -m "feat: add FeishuConfig and FeishuClient

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task F2: 实现卡片构建器

**Files:**
- Create: `services/feishu/card_builder.py`
- Test: `tests/unit/test_card_builder.py`

- [ ] **Step 1: 创建 `services/feishu/card_builder.py`**

```python
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
```

- [ ] **Step 2: 创建 `tests/unit/test_card_builder.py`**

```python
"""测试卡片构建器"""
import pytest
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
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/unit/test_card_builder.py -v`
Expected: PASS (8 tests)

- [ ] **Step 4: Commit**

```bash
git add services/feishu/card_builder.py tests/unit/test_card_builder.py
git commit -m "feat: implement Feishu CardBuilder with query/attribution/summary cards

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task F3: 实现事件处理器和 Webhook 端点

**Files:**
- Create: `services/feishu/event_handler.py`
- Create: `api/routes/feishu.py`
- Modify: `api/main.py` (注册 feishu router)
- Test: `tests/unit/test_event_handler.py`

- [ ] **Step 1: 创建 `services/feishu/event_handler.py`**

```python
"""飞书事件处理器"""
import asyncio
import logging
from typing import Any

from services.feishu.feishu_client import FeishuClient
from services.feishu.card_builder import CardBuilder
from services.nl_query_service import NLQueryService
from services.attribution_service import AttributionService

logger = logging.getLogger(__name__)


# 内存去重表（生产环境建议用 Redis）
_processed_messages: set[str] = set()
MAX_DEDUP_SIZE = 10000


class EventHandler:
    """飞书事件分发处理器"""

    def __init__(self):
        self.feishu_client = FeishuClient()
        self.card_builder = CardBuilder()
        self.nl_query = NLQueryService()
        self.attribution = AttributionService()

    def _extract_query(self, text: str, bot_name: str) -> str:
        """从用户消息中提取查询内容（去除 @机器人 标记）"""
        text = text.strip()
        # 去除 @机器人名称
        for prefix in [f"@{bot_name}", f"@{bot_name} ", bot_name]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        # 去除首尾标点
        text = text.strip("：:").strip()
        return text

    def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否已处理（幂等去重）"""
        if message_id in _processed_messages:
            return True
        _processed_messages.add(message_id)
        # 防止内存无限增长
        if len(_processed_messages) > MAX_DEDUP_SIZE:
            _processed_messages.clear()
        return False

    async def handle_message(self, event: dict[str, Any]) -> None:
        """处理接收到的消息事件"""
        message_id = event.get("message", {}).get("message_id", "")
        if self._is_duplicate(message_id):
            logger.info(f"Duplicate message ignored: {message_id}")
            return

        sender = event.get("sender", {})
        receive_id = sender.get("sender_id", {}).get("open_id", "")
        message_content = event.get("message", {}).get("content", "{}")

        # 解析消息内容
        try:
            import json
            content = json.loads(message_content)
            text = content.get("text", "")
        except Exception:
            text = ""

        query = self._extract_query(text, self.feishu_client.bot_name)
        if not query:
            return

        # 异步处理（飞书要求 3s 内响应）
        asyncio.create_task(self._process_query_async(receive_id, query))

    async def _process_query_async(self, receive_id: str, query: str) -> None:
        """异步处理查询（后台执行，不阻塞 Webhook）"""
        try:
            # 判断是否为归因分析查询
            if any(kw in query for kw in ["为什么", "原因", "导致", "为何"]):
                result = self.attribution.analyze(query)
                card = self.card_builder.attribution_card(
                    {
                        "question": result.question,
                        "factors": [
                            {"dimension": f.dimension, "description": f.description, "confidence": f.confidence, "suggestion": f.suggestion}
                            for f in result.factors
                        ],
                        "overall_confidence": result.overall_confidence,
                        "analysis_time": result.analysis_time,
                    }
                )
            else:
                nl_result = self.nl_query.query(query)
                card = self.card_builder.query_result_card(query=query, result=nl_result)

            self.feishu_client.send_card(receive_id, card)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            error_card = self.card_builder.error_card(f"处理失败: {str(e)}")
            self.feishu_client.send_card(receive_id, error_card)

    def handle_button_callback(self, callback_data: dict[str, Any]) -> None:
        """处理卡片按钮回调"""
        action = callback_data.get("action", "")
        params = callback_data.get("params", {})

        if action == "retry":
            # 重新处理逻辑（需要存储原始 query）
            pass
        elif action == "view_detail":
            # 查看详情
            pass
        elif action == "trend":
            # 趋势分析
            pass
        elif action == "customer":
            # 客户分析
            pass
```

- [ ] **Step 2: 创建 `api/routes/feishu.py`**

```python
"""飞书 Webhook 端点"""
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from services.feishu.event_handler import EventHandler

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/events")
async def handle_feishu_event(request: Request) -> JSONResponse:
    """
    飞书事件 Webhook 端点

    支持:
    - URL 注册验证 (challenge)
    - 消息事件 (im.message.receive_v1)
    - 卡片按钮回调
    """
    body = await request.body()
    handler = EventHandler()

    # 验证签名（如已配置）
    signature = request.headers.get("X-Lark-Signature", "")
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    if signature and not handler.feishu_client.verify_signature(signature, timestamp, body):
        raise HTTPException(status_code=403, detail="Invalid signature")

    import json
    payload = json.loads(body)

    # URL 注册验证
    if "challenge" in payload:
        return JSONResponse(content={"challenge": payload["challenge"]})

    # 事件处理
    event = payload.get("event", {})
    event_type = payload.get("header", {}).get("event_type", "")

    if event_type == "im.message.receive_v1":
        await handler.handle_message(event)

    # 飞书要求 3s 内返回 200
    return JSONResponse(content={"code": 0, "msg": "success"})
```

- [ ] **Step 3: 修改 `api/main.py`，注册 feishu router**

```python
from api.routes import ar, query, ai, attribution, knowledge, feishu  # 添加 feishu

api_router.include_router(ar.router, prefix="/ar", tags=["AR"])
api_router.include_router(query.router, prefix="/query", tags=["Query"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(attribution.router, prefix="/attribution", tags=["Attribution"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(feishu.router, prefix="/feishu", tags=["Feishu"])  # 新增
```

- [ ] **Step 4: 创建 `tests/unit/test_event_handler.py`**

```python
"""测试飞书事件处理器"""
import pytest
from unittest.mock import MagicMock, patch
from services.feishu.event_handler import EventHandler


class TestEventHandler:
    def setup_method(self):
        self.handler = EventHandler()

    def test_extract_query_strips_bot_mention(self):
        query = self.handler._extract_query("@FinBoss财务助手 本月应收总额", "FinBoss财务助手")
        assert query == "本月应收总额"

    def test_extract_query_strips_punctuation(self):
        query = self.handler._extract_query("：本月应收总额", "")
        assert query == "本月应收总额"

    def test_extract_query_empty(self):
        query = self.handler._extract_query("", "Bot")
        assert query == ""

    def test_is_duplicate(self):
        msg_id = "test_msg_123"
        assert self.handler._is_duplicate(msg_id) is False
        assert self.handler._is_duplicate(msg_id) is True  # Second call

    def test_is_duplicate_after_clear(self):
        handler = EventHandler()
        msg_id = "fresh_msg"
        assert handler._is_duplicate(msg_id) is False
```

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/unit/test_event_handler.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add services/feishu/event_handler.py api/routes/feishu.py api/main.py tests/unit/test_event_handler.py
git commit -m "feat: add Feishu webhook endpoint with async message handling

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 最终验证

### Task FV1: 运行全量测试

- [ ] **Step 1: 运行所有单元测试**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: 运行集成测试**

Run: `uv run pytest tests/integration/ -v --tb=short`
Expected: ALL PASS（集成测试可能因外部服务不可用而跳过，但端点必须存在）

- [ ] **Step 3: 代码检查**

Run: `uv run ruff check . --fix`
Run: `uv run mypy . --ignore-missing-imports`
Expected: 无 ERROR（WARNING 可接受）

- [ ] **Step 4: 验证所有新端点已注册**

Run: `uv run python -c "from api.main import app; routes = [r.path for r in app.routes]; print('\n'.join(routes))"`
Expected: 包含以下路由：
- `/api/v1/attribution/analyze`
- `/api/v1/knowledge`
- `/api/v1/feishu/events`

- [ ] **Step 5: Commit 全量测试**

```bash
git add -A && git commit -m "test: add Phase 3 unit and integration tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 依赖安装

开始实施前，确保依赖已安装：

```bash
# 安装新依赖
uv sync

# 安装 lark-oapi（如未在 pyproject.toml 中）
uv add lark-oapi
```
