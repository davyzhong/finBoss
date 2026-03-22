# Phase 7C 实现计划 — AI 根因分析 + 异常聚合视图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 为数据质量模块添加 AI 根因分析和多维度异常聚合视图两个功能。

**架构:**
- `services/ai_analysis_service.py` — 新建 AI 分析服务，封装 prompt 构造、LLM 调用（Ollama/OpenAI 双模式）、结果解析
- `services/field_quality_service.py` — 新增 `analyze_anomaly()` 和 `get_aggregated_anomalies()` 方法
- `api/routes/quality.py` — 新增 `POST /anomalies/{id}/analyze` 和 `GET /anomalies/aggregated` 端点
- `schemas/quality.py` 和 `api/schemas/quality.py` — 新增字段和 schema
- DDL 通过 `scripts/phase7c_ddl.sql` + `scripts/init_phase7c.py` 幂等执行

**技术栈:** Python 3.11, FastAPI, ClickHouse, Ollama, httpx, Pydantic

---

## 文件变更总览

| 文件 | 操作 |
|------|------|
| `schemas/quality.py` | 修改 — 新增 `root_cause`、`analyzed_at`、`model_used` 字段 |
| `api/schemas/quality.py` | 修改 — 新增 `RootCauseAnalysisResponse`、`AggregatedAnomalyGroup`、`AggregatedAnomaliesResponse` |
| `api/config.py` | 修改 — 新增 `AIAnalysisConfig` 类和 `Settings` 引用 |
| `.env.example` | 修改 — 新增 `QUALITY_AI_*` 环境变量 |
| `services/ai_analysis_service.py` | 新建 — AI 根因分析核心逻辑 |
| `services/field_quality_service.py` | 修改 — 新增 `analyze_anomaly()`、`get_aggregated_anomalies()`、`check_all()` 增加自动分析 |
| `api/routes/quality.py` | 修改 — 新增两个端点 |
| `scripts/phase7c_ddl.sql` | 新建 — DDL 语句 |
| `scripts/init_phase7c.py` | 新建 — 幂等初始化脚本 |
| `tests/unit/test_ai_analysis_service.py` | 新建 — 单元测试 |
| `tests/integration/test_quality_api.py` | 修改 — 新增集成测试 |

---

## Task 1: 配置和 Schema 准备

**Files:**
- Modify: `api/config.py` (在 QualityAlertConfig 之后添加 AIAnalysisConfig)
- Modify: `schemas/quality.py` (QualityAnomaly 新增 3 字段)
- Modify: `api/schemas/quality.py` (新增 3 个 Response schema)
- Modify: `.env.example` (新增 QUALITY_AI_* 环境变量)

- [ ] **Step 1: 在 `api/config.py` 的 `QualityAlertConfig` 后添加 `AIAnalysisConfig`**

```python
class AIAnalysisConfig(BaseSettings):
    """AI 根因分析配置"""

    model_config = SettingsConfigDict(
        env_prefix="quality_ai_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_model: str = Field(default="qwen2.5:7b", description="Ollama 默认模型")
    use_openai: bool = Field(default=False, description="切换到 OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI 模型名")
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    auto_analyze_high_severity: bool = Field(default=True, description="自动分析高危异常")
```

- [ ] **Step 2: 在 `Settings` 类中添加 `ai_analysis: AIAnalysisConfig` 字段**

在 `api/config.py` 的 `Settings` 类里，`quality_alert` 字段后加一行：
```python
ai_analysis: AIAnalysisConfig = Field(default_factory=AIAnalysisConfig)
```

- [ ] **Step 3: 在 `schemas/quality.py` 的 `QualityAnomaly` 中新增 3 字段**

在 `sla_hours: float = 0.0` 后添加：
```python
    root_cause: str = ""
    analyzed_at: datetime | None = None
    model_used: str = ""
```

- [ ] **Step 4: 在 `api/schemas/quality.py` 末尾添加新 schema**

```python
class RootCauseAnalysisResponse(BaseModel):
    anomaly_id: str
    root_cause: str
    suggestions: list[str]
    confidence: Literal["high", "medium", "low"]
    model_used: str
    analyzed_at: datetime


class AggregatedAnomalyItem(BaseModel):
    id: str
    table_name: str
    column_name: str
    severity: str
    status: str
    assignee: str
    created_at: date


class AggregatedAnomalyGroup(BaseModel):
    key: str
    total: int
    high: int
    medium: int
    low: int
    unassigned: int
    oldest_age_days: int
    items: list[AggregatedAnomalyItem]


class AggregatedAnomaliesResponse(BaseModel):
    groups: list[AggregatedAnomalyGroup]
    total_anomalies: int
```

- [ ] **Step 5: 在 `.env.example` 末尾 Phase 7B 区块后添加**

```bash
# ===========================================
# Phase 7C — AI 根因分析
# ===========================================

QUALITY_AI_DEFAULT_MODEL=qwen2.5:7b
QUALITY_AI_USE_OPENAI=false
QUALITY_AI_OPENAI_MODEL=gpt-4o-mini
QUALITY_AI_OPENAI_API_KEY=
QUALITY_AI_AUTO_ANALYZE_HIGH_SEVERITY=true
```

- [ ] **Step 6: Commit**

```bash
git add api/config.py schemas/quality.py api/schemas/quality.py .env.example
git commit -m "feat(7C): add AIAnalysisConfig and new quality schemas"
```

---

## Task 2: DDL 和初始化脚本

**Files:**
- Create: `scripts/phase7c_ddl.sql`
- Create: `scripts/init_phase7c.py`

- [ ] **Step 1: 创建 `scripts/phase7c_ddl.sql`**

```sql
-- Phase 7C: AI 根因分析字段
ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS root_cause String DEFAULT '';

ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS analyzed_at DateTime DEFAULT now();

ALTER TABLE dm.quality_anomalies
ADD COLUMN IF NOT EXISTS model_used String DEFAULT '';
```

- [ ] **Step 2: 创建 `scripts/init_phase7c.py`**

参考 `scripts/init_phase7b.py` 的模式，创建幂等脚本：
- 读取 `scripts/phase7c_ddl.sql`
- 连接 ClickHouse 执行每条 ALTER 语句
- 捕获异常码 44（字段已存在）视为成功
- 其他异常输出警告但不中断
- 打印成功/跳过信息

```python
"""Phase 7C DDL 初始化脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.clickhouse_service import ClickHouseDataService

DDL_FILE = Path(__file__).parent / "phase7c_ddl.sql"


def run_ddl(ch: ClickHouseDataService) -> None:
    sql_text = DDL_FILE.read_text(encoding="utf-8")
    for statement in sql_text.split(";"):
        stmt = statement.strip()
        if not stmt:
            continue
        full_stmt = stmt + ";"
        try:
            ch.execute(full_stmt)
            print(f"  OK: {stmt[:60]}")
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 44 or "already exists" in str(e).lower():
                print(f" SKIP: {stmt[:60]} (already exists)")
            else:
                print(f"  WARN: {stmt[:60]} -> {e}")


if __name__ == "__main__":
    print("Running Phase 7C DDL...")
    ch = ClickHouseDataService()
    run_ddl(ch)
    print("Done.")
```

- [ ] **Step 3: 运行脚本验证**

```bash
uv run python scripts/init_phase7c.py
```
预期：输出 OK/SKIP，无报错

- [ ] **Step 4: Commit**

```bash
git add scripts/phase7c_ddl.sql scripts/init_phase7c.py
git commit -m "feat(7C): add Phase 7C DDL and init script"
```

---

## Task 3: AI 分析服务

**Files:**
- Create: `services/ai_analysis_service.py`
- Test: `tests/unit/test_ai_analysis_service.py`

- [ ] **Step 1: 写失败的单元测试 `tests/unit/test_ai_analysis_service.py`**

```python
"""AI 分析服务单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestAIGenAnalysisService:
    def test_build_prompt_includes_context(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        prompt = svc._build_prompt(
            table_name="std.std_ar",
            column_name="ar_amount",
            metric="null_rate",
            value=0.35,
            threshold=0.20,
            duration_days=5,
            context={},
        )
        assert "std.std_ar" in prompt
        assert "ar_amount" in prompt
        assert "0.35" in prompt or "35%" in prompt

    def test_parse_llm_response_valid_json(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        raw = '{"root_cause":"数据源导出问题","suggestions":["检查上游接口","修复ETL任务"],"confidence":"high"}'
        result = svc._parse_response(raw)
        assert result["root_cause"] == "数据源导出问题"
        assert len(result["suggestions"]) == 2
        assert result["confidence"] == "high"

    def test_parse_llm_response_with_markdown_fence(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        raw = '```json\n{"root_cause":"test","suggestions":["a"],"confidence":"medium"}\n```'
        result = svc._parse_response(raw)
        assert result["root_cause"] == "test"

    def test_parse_llm_response_invalid_json(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService()
        result = svc._parse_response("not json at all")
        assert result["root_cause"] == ""
        assert result["confidence"] == "low"

    def test_ollama_mode_default(self):
        from services.ai_analysis_service import AIGenAnalysisService
        svc = AIGenAnalysisService(use_openai=False)
        assert svc._use_openai is False
        assert svc._model == "qwen2.5:7b"

    @patch("services.ai_analysis_service.OllamaService")
    def test_analyze_calls_ollama(self, mock_ollama_cls):
        from services.ai_analysis_service import AIGenAnalysisService
        mock_instance = MagicMock()
        mock_instance.generate.return_value = '{"root_cause":"test","suggestions":["a"],"confidence":"medium"}'
        mock_ollama_cls.return_value = mock_instance
        svc = AIGenAnalysisService(use_openai=False)
        result = svc.analyze(
            table_name="std.std_ar",
            column_name="ar_amount",
            metric="null_rate",
            value=0.35,
            threshold=0.20,
            duration_days=5,
        )
        mock_instance.generate.assert_called_once()
        assert result["root_cause"] == "test"
        assert result["model_used"] == "ollama"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
uv run pytest tests/unit/test_ai_analysis_service.py -v
```
预期：FAIL — `AIGenAnalysisService` 未定义

- [ ] **Step 3: 实现 `services/ai_analysis_service.py`**

```python
"""AI 根因分析服务"""
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """你是一位数据质量专家。以下是某张表的字段异常信息：
- 表名: {table_name}
- 异常字段: {column_name}
- 异常类型: {metric}
- 当前值: {value_str}
- 阈值: {threshold_str}
- 异常持续天数: {duration_days}天

请分析可能的技术原因（数据源、ETL、Schema变更等），并给出1-3条可操作的修复建议。

返回JSON格式（不要包含其他内容）：
{{"root_cause": "...", "suggestions": ["建议1", "建议2"], "confidence": "high|medium|low"}}
"""


class AIGenAnalysisService:
    """AI 根因分析服务（支持 Ollama / OpenAI 双模式）"""

    def __init__(
        self,
        use_openai: bool | None = None,
        default_model: str = "qwen2.5:7b",
        openai_model: str = "gpt-4o-mini",
        openai_api_key: str = "",
    ):
        # 延迟导入避免循环依赖
        from api.config import get_settings
        settings = get_settings()
        cfg = settings.ai_analysis

        self._use_openai = use_openai if use_openai is not None else cfg.use_openai
        self._default_model = default_model or cfg.default_model
        self._openai_model = openai_model or cfg.openai_model
        self._openai_api_key = openai_api_key or cfg.openai_api_key

    @property
    def _model(self) -> str:
        return self._openai_model if self._use_openai else self._default_model

    def _build_prompt(
        self,
        table_name: str,
        column_name: str,
        metric: str,
        value: float,
        threshold: float,
        duration_days: int,
        context: dict[str, Any],
    ) -> str:
        # 格式化值
        if metric in ("null_rate", "distinct_rate", "negative_rate"):
            value_str = f"{value * 100:.1f}%"
            threshold_str = f"{threshold * 100:.1f}%"
        else:
            value_str = f"{value}"
            threshold_str = f"{threshold}"

        prompt = PROMPT_TEMPLATE.format(
            table_name=table_name,
            column_name=column_name,
            metric=metric,
            value_str=value_str,
            threshold_str=threshold_str,
            duration_days=duration_days,
        )
        return prompt

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        text = raw.strip()
        # 去除 markdown code fence
        for fence in ("```json", "```JSON", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
            if text.endswith(fence):
                text = text[: -len(fence)]
        text = text.strip()
        try:
            data = json.loads(text)
            return {
                "root_cause": str(data.get("root_cause", "")),
                "suggestions": list(data.get("suggestions", [])),
                "confidence": str(data.get("confidence", "low")),
            }
        except json.JSONDecodeError:
            logger.warning("LLM response is not valid JSON: %s", raw[:100])
            return {"root_cause": "", "suggestions": [], "confidence": "low"}

    def analyze(
        self,
        table_name: str,
        column_name: str,
        metric: str,
        value: float,
        threshold: float,
        duration_days: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行根因分析，返回解析后的结果"""
        prompt = self._build_prompt(
            table_name, column_name, metric, value, threshold, duration_days, context or {}
        )
        if self._use_openai:
            raw = self._call_openai(prompt)
        else:
            raw = self._call_ollama(prompt)
        result = self._parse_response(raw)
        result["model_used"] = "openai" if self._use_openai else "ollama"
        return result

    def _call_ollama(self, prompt: str) -> str:
        from services.ai.ollama_service import OllamaService
        svc = OllamaService(model=self._default_model)
        result = svc.generate(prompt)
        return result

    def _call_openai(self, prompt: str) -> str:
        if not self._openai_api_key:
            raise ValueError("OpenAI API key not configured")
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 512,
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
uv run pytest tests/unit/test_ai_analysis_service.py -v
```
预期：PASS（5/5）

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_ai_analysis_service.py services/ai_analysis_service.py
git commit -m "feat(7C): add AI root cause analysis service"
```

---

## Task 4: FieldQualityService — 分析和聚合方法

**Files:**
- Modify: `services/field_quality_service.py` (新增 3 个方法)
- Test: `tests/unit/test_quality_trend_sla.py` (新增聚合视图测试)

- [ ] **Step 1: 读取 `field_quality_service.py` 末尾，了解现有方法结构**

读取 `services/field_quality_service.py` 全部内容，找到 `list_anomalies`、`update_anomaly`、`send_quality_digest` 方法位置。

- [ ] **Step 2: 添加 `analyze_anomaly` 方法**

在 `send_quality_digest` 方法后添加：

```python
def analyze_anomaly(self, anomaly_id: str) -> dict[str, Any] | None:
    """对指定异常执行 AI 根因分析"""
    from services.ai_analysis_service import AIGenAnalysisService

    rows = self._ch.execute_query(
        "SELECT * FROM dm.quality_anomalies WHERE id = %(id)s LIMIT 1",
        {"id": anomaly_id}
    )
    if not rows:
        return None
    row = rows[0]

    # 计算持续天数
    detected: datetime = row["detected_at"]
    duration_days = max(1, (datetime.now() - detected).days)

    # 调用 AI 分析
    ai_svc = AIGenAnalysisService()
    result = ai_svc.analyze(
        table_name=row["table_name"],
        column_name=row["column_name"],
        metric=row["metric"],
        value=float(row["value"]),
        threshold=float(row["threshold"]),
        duration_days=duration_days,
    )

    # 写入 ClickHouse
    now = datetime.now()
    self._ch.execute(
        "INSERT INTO dm.quality_anomalies "
        "(id, report_id, stat_date, table_name, column_name, metric, value, threshold, "
        "severity, status, detected_at, resolved_at, assignee, sla_hours, "
        "root_cause, analyzed_at, model_used) "
        "VALUES "
        "(%(id)s, %(report_id)s, %(stat_date)s, %(table_name)s, %(column_name)s, %(metric)s, "
        "%(value)s, %(threshold)s, %(severity)s, %(status)s, %(detected_at)s, %(resolved_at)s, "
        "%(assignee)s, %(sla_hours)s, %(root_cause)s, %(analyzed_at)s, %(model_used)s)",
        {
            "id": anomaly_id,
            "report_id": row["report_id"],
            "stat_date": row["stat_date"],
            "table_name": row["table_name"],
            "column_name": row["column_name"],
            "metric": row["metric"],
            "value": row["value"],
            "threshold": row["threshold"],
            "severity": row["severity"],
            "status": row["status"],
            "detected_at": row["detected_at"],
            "resolved_at": row.get("resolved_at"),
            "assignee": row.get("assignee", ""),
            "sla_hours": row.get("sla_hours", 0.0),
            "root_cause": result["root_cause"],
            "analyzed_at": now,
            "model_used": result["model_used"],
        }
    )

    result["anomaly_id"] = anomaly_id
    result["analyzed_at"] = now.isoformat()
    return result
```

- [ ] **Step 3: 添加 `get_aggregated_anomalies` 方法**

在 `analyze_anomaly` 后添加：

```python
def get_aggregated_anomalies(
    self,
    group_by: list[str],
    status: str | None = None,
    min_severity: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """多维度异常聚合视图"""
    # 构建 WHERE 子句（SQL 注入安全）
    conditions = []
    params: dict[str, Any] = {}
    if status:
        conditions.append("status = %(status)s")
        params["status"] = status
    if min_severity:
        sev_order = {"高": 3, "中": 2, "低": 1}
        min_val = sev_order.get(min_severity, 1)
        sev_filter = " OR ".join(
            f"severity = %(sev_{i})" for i, _ in enumerate(list(sev_order.keys())[:min_val])
        )
        conditions.append(f"({sev_filter})")
        for i, k in enumerate(list(sev_order.keys())[:min_val]):
            params[f"sev_{i}"] = k

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 查询基础数据（带 ORDER BY 防止乱序）
    base_sql = (
        "SELECT id, table_name, column_name, metric, value, threshold, severity, "
        "status, assignee, detected_at "
        "FROM dm.quality_anomalies "
        f"{where_clause} "
        "ORDER BY detected_at DESC"
    )
    rows = self._ch.execute_query(base_sql, params)
    if not rows:
        return {"groups": [], "total_anomalies": 0}

    # 按 group_by 维度分组
    groups_map: dict[str, dict[str, Any]] = {}
    sev_order = {"高": 3, "中": 2, "低": 1}
    now_dt = datetime.now()

    for row in rows:
        # 生成复合 key
        key_parts = []
        for dim in group_by:
            if dim == "table":
                key_parts.append(row["table_name"])
            elif dim == "assignee":
                key_parts.append(row["assignee"] or "(unassigned)")
            elif dim == "severity":
                key_parts.append(row["severity"])
        key = "::".join(key_parts) if key_parts else "all"

        if key not in groups_map:
            groups_map[key] = {
                "key": key,
                "total": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "unassigned": 0,
                "oldest_age_days": 0,
                "items": [],
            }
        g = groups_map[key]
        g["total"] += 1
        sev = row["severity"]
        g[sev] = g.get(sev, 0) + 1
        if not row["assignee"]:
            g["unassigned"] += 1

        detected: datetime = row["detected_at"]
        age_days = (now_dt - detected).days
        if age_days > g["oldest_age_days"]:
            g["oldest_age_days"] = age_days

        if len(g["items"]) < limit:
            g["items"].append({
                "id": row["id"],
                "table_name": row["table_name"],
                "column_name": row["column_name"],
                "severity": row["severity"],
                "status": row["status"],
                "assignee": row["assignee"] or "",
                "created_at": detected.date().isoformat() if hasattr(detected, "date") else str(detected)[:10],
            })

    groups = list(groups_map.values())
    total = sum(g["total"] for g in groups)
    return {"groups": groups, "total_anomalies": total}
```

- [ ] **Step 4: 修改 `check_all()` 方法，在扫描结束后自动分析高危异常**

在 `check_all()` 末尾（return 之前）添加：

```python
# 自动分析高危未分析异常
from api.config import get_settings
if get_settings().ai_analysis.auto_analyze_high_severity:
    unanalyzed = self._ch.execute_query(
        "SELECT id FROM dm.quality_anomalies "
        "WHERE severity = '高' AND root_cause = '' "
        "LIMIT 10"
    )
    for row in unanalyzed:
        try:
            self.analyze_anomaly(row["id"])
        except Exception:
            pass  # 不阻塞扫描主流程
```

**注意**：由于 `check_all()` 方法很长，建议直接在 `return result` 前插入上面代码块。

- [ ] **Step 5: 在 `tests/unit/test_quality_trend_sla.py` 末尾添加聚合视图测试**

```python
class TestAggregatedAnomalies:
    def test_group_by_table(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = [
                {"id": "1", "table_name": "std.std_ar", "column_name": "ar_amount",
                 "metric": "null_rate", "value": 0.3, "threshold": 0.2,
                 "severity": "高", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
                {"id": "2", "table_name": "std.std_ar", "column_name": "due_date",
                 "metric": "null_rate", "value": 0.25, "threshold": 0.2,
                 "severity": "中", "status": "open", "assignee": "",
                 "detected_at": datetime.now()},
                {"id": "3", "table_name": "dm.dm_customer360", "column_name": "ar_overdue",
                 "metric": "null_rate", "value": 0.15, "threshold": 0.2,
                 "severity": "低", "status": "open", "assignee": "li",
                 "detected_at": datetime.now()},
            ]
            result = svc.get_aggregated_anomalies(group_by=["table"])
            assert result["total_anomalies"] == 3
            keys = {g["key"] for g in result["groups"]}
            assert "std.std_ar" in keys
            assert "dm.dm_customer360" in keys
            std_ar_group = next(g for g in result["groups"] if g["key"] == "std.std_ar")
            assert std_ar_group["total"] == 2
            assert std_ar_group["high"] == 1
            assert std_ar_group["medium"] == 1
            assert std_ar_group["unassigned"] == 1

    def test_group_by_assignee(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = [
                {"id": "1", "table_name": "std.std_ar", "column_name": "ar_amount",
                 "metric": "null_rate", "value": 0.3, "threshold": 0.2,
                 "severity": "高", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
                {"id": "2", "table_name": "std.std_ar", "column_name": "due_date",
                 "metric": "null_rate", "value": 0.25, "threshold": 0.2,
                 "severity": "中", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
            ]
            result = svc.get_aggregated_anomalies(group_by=["assignee"])
            zhang_group = next(g for g in result["groups"] if g["key"] == "zhang")
            assert zhang_group["total"] == 2

    def test_empty_result(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = []
            result = svc.get_aggregated_anomalies(group_by=["table"])
            assert result["groups"] == []
            assert result["total_anomalies"] == 0
```

- [ ] **Step 6: 运行测试**

```bash
uv run pytest tests/unit/test_quality_trend_sla.py -v
```
预期：全部 PASS

- [ ] **Step 7: Commit**

```bash
git add services/field_quality_service.py tests/unit/test_quality_trend_sla.py
git commit -m "feat(7C): add analyze_anomaly and get_aggregated_anomalies"
```

---

## Task 5: API 路由

**Files:**
- Modify: `api/routes/quality.py`

- [ ] **Step 1: 在 `api/routes/quality.py` 添加两个新端点**

在 `update_anomaly` 端点后（`send_quality_digest` 端点之前）添加：

```python
@router.post("/anomalies/{anomaly_id}/analyze", response_model=RootCauseAnalysisResponse)
async def analyze_anomaly(
    anomaly_id: str,
    service: FieldQualityServiceDep,
):
    """对指定异常执行 AI 根因分析"""
    from api.schemas.quality import RootCauseAnalysisResponse
    from datetime import datetime

    result = service.analyze_anomaly(anomaly_id)
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return RootCauseAnalysisResponse(
        anomaly_id=anomaly_id,
        root_cause=result["root_cause"],
        suggestions=result["suggestions"],
        confidence=result["confidence"],
        model_used=result["model_used"],
        analyzed_at=datetime.fromisoformat(result["analyzed_at"]) if result.get("analyzed_at") else datetime.now(),
    )


@router.get("/anomalies/aggregated", response_model=AggregatedAnomaliesResponse)
async def get_aggregated_anomalies(
    service: FieldQualityServiceDep,
    group_by: Annotated[str, Query(description="聚合维度，逗号分隔，如 table,severity")] = "table",
    status: Literal["open", "resolved", "ignored"] | None = Query(default=None),
    min_severity: Literal["高", "中", "低"] | None = Query(default=None),
    limit: int = Query(default=50, le=500),
):
    """多维度异常聚合视图"""
    from api.schemas.quality import AggregatedAnomaliesResponse
    dims = [d.strip() for d in group_by.split(",") if d.strip()]
    result = service.get_aggregated_anomalies(dims, status, min_severity, limit)
    return AggregatedAnomaliesResponse(**result)
```

- [ ] **Step 2: 在文件顶部添加缺少的导入**

确认 `api/routes/quality.py` 已有：
```python
from typing import Annotated, Literal
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query
```

确保新增端点引用的 schema 都已导入（如果没有则在文件顶部加）：
```python
from api.schemas.quality import (
    AnomalyUpdateRequest,
    CheckResponse,
    QualityHistoryResponse,
    QualitySummaryResponse,
    SendDigestResponse,
    RootCauseAnalysisResponse,    # 新增
    AggregatedAnomaliesResponse,   # 新增
)
```

- [ ] **Step 3: 测试路由可导入**

```bash
uv run python -c "from api.routes.quality import router; print('OK')"
```
预期：OK

- [ ] **Step 4: Commit**

```bash
git add api/routes/quality.py
git commit -m "feat(7C): add analyze and aggregated endpoints"
```

---

## Task 6: 集成测试

**Files:**
- Modify: `tests/integration/test_quality_api.py`

- [ ] **Step 1: 添加集成测试**

在 `test_quality_api.py` 末尾添加：

```python
def test_analyze_anomaly_not_found(client, ch_container):
    response = client.post("/quality/anomalies/nonexistent-id/analyze")
    assert response.status_code == 404


def test_aggregated_anomalies_empty(client, ch_container):
    response = client.get("/quality/anomalies/aggregated?group_by=table")
    assert response.status_code == 200
    data = response.json()
    assert "groups" in data
    assert "total_anomalies" in data


def test_aggregated_anomalies_group_by_assignee(client, ch_container):
    response = client.get("/quality/anomalies/aggregated?group_by=assignee")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["groups"], list)


def test_aggregated_anomalies_multiple_dimensions(client, ch_container):
    response = client.get("/quality/anomalies/aggregated?group_by=table,severity&status=open")
    assert response.status_code == 200
    data = response.json()
    assert data["total_anomalies"] >= 0
```

- [ ] **Step 2: 运行集成测试**

```bash
uv run pytest tests/integration/test_quality_api.py -v
```
预期：全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_quality_api.py
git commit -m "test(7C): add integration tests for analyze and aggregated endpoints"
```

---

## Task 7: 飞书卡片增强（根因展示）

**Files:**
- Modify: `templates/reports/quality_report.html.j2`

- [ ] **Step 1: 在 HTML 模板 anomaly 表格中新增根因列**

在 anomaly 表格的 `<thead>` 的 `<tr>` 中，在 `SLA` 列后添加：
```html
<th>根因</th>
```

在 `<tbody>` 的循环中，在 SLA td 后添加：
```html
<td>
  {% if anomaly.root_cause %}
    <span title="{{ anomaly.root_cause }}">{{ anomaly.root_cause[:30] }}...</span>
  {% else %}
    <span style="color:#ccc">未分析</span>
  {% endif %}
</td>
```

**注意**：如果 HTML 模板使用 JavaScript 渲染表格，则在 JS 的 anomaly 对象中添加 root_cause 字段，并在渲染逻辑中增加对应列。

- [ ] **Step 2: Commit**

```bash
git add templates/reports/quality_report.html.j2
git commit -m "feat(7C): show root cause in quality report template"
```

---

## Task 8: 全量验证

- [ ] **Step 1: 运行完整测试套件**

```bash
uv run pytest tests/ -v --tb=short
```

- [ ] **Step 2: 确认无报错，全部通过**

- [ ] **Step 3: 代码风格检查**

```bash
uv run ruff check services/ai_analysis_service.py services/field_quality_service.py api/routes/quality.py
uv run ruff format --check services/ai_analysis_service.py services/field_quality_service.py api/routes/quality.py
```

- [ ] **Step 4: 最终 Commit（如有未提交的变更）**

```bash
git status
git add -A && git commit -m "feat(7C): complete AI root cause and anomaly aggregation"
```
