# Phase 7C 数据质量增强 — 设计规格

> **日期**: 2026-03-22
> **范围**: B（AI根因分析）+ C（异常聚合视图）

---

## B：AI 根因分析

### 1. 触发方式

- **自动触发**：质量扫描（`check_all`）完成后，对 `severity=高` 且 `root_cause` 为空的异常自动调用分析
- **手动触发**：`POST /quality/anomalies/{id}/analyze` API

### 2. 分析流程

1. 查询异常上下文：同表近期（7天）其他异常 + 字段统计值（均值、标准差、NULL率）
2. 构造 prompt（见下）
3. 调用 LLM（Ollama 默认，OpenAI 可配置切换）
4. 解析 JSON 结果，写入 `dm.quality_anomalies.root_cause`、`analyzed_at`、`model_used`
5. 生成飞书卡片推送

### 3. Prompt 模板

```
你是一位数据质量专家。以下是某张表的字段异常信息：
- 表名: {table_name}
- 异常字段: {field_name}
- 异常类型: {anomaly_type}
- 当前值: {current_value}
- 正常范围: {expected_range}
- 异常持续天数: {duration_days}天

请分析可能的技术原因（数据源、ETL、Schema变更等），
并给出1-3条可操作的修复建议。

返回JSON格式：
{
  "root_cause": "...",
  "suggestions": ["建议1", "建议2", "建议3"],
  "confidence": "high|medium|low"
}
```

### 4. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/quality/anomalies/{id}/analyze` | 手动触发单条根因分析 |

**响应**
```json
{
  "anomaly_id": "uuid",
  "root_cause": "...",
  "suggestions": ["建议1", "建议2"],
  "confidence": "high",
  "model_used": "ollama",
  "analyzed_at": "2026-03-22T10:00:00"
}
```

### 5. ClickHouse Schema 变更

```sql
ALTER TABLE dm.quality_anomalies
ADD COLUMN root_cause String DEFAULT '',
ADD COLUMN analyzed_at DateTime DEFAULT now(),
ADD COLUMN model_used String DEFAULT '';
```

### 6. 配置项（`api/config.py`）

```python
class AIAnalysisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="quality_ai_", extra="ignore")
    default_model: str = "qwen2.5:7b"       # Ollama 模型
    use_openai: bool = False                  # 切换到 OpenAI
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    auto_analyze_high_severity: bool = True   # 自动分析高危
```

---

## C：异常聚合视图

### 1. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/quality/anomalies/aggregated` | 聚合视图 |

**查询参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `group_by` | string | 聚合维度，`table`、`assignee`、`severity`，支持组合如 `table,severity` |
| `status` | string | `open`、`resolved`、`ignored` |
| `min_severity` | string | 最小级别过滤：`高`、`中`、`低` |
| `limit` | int | 每组最多返回条数，默认 50 |

### 2. 响应结构

```json
{
  "groups": [
    {
      "key": "std.std_ar",
      "total": 5,
      "high": 1,
      "medium": 2,
      "low": 2,
      "unassigned": 1,
      "oldest_age_days": 12,
      "items": [
        {
          "id": "uuid",
          "table_name": "std.std_ar",
          "field_name": "ar_amount",
          "severity": "高",
          "status": "open",
          "assignee": "zhangsan",
          "created_at": "2026-03-10"
        }
      ]
    }
  ],
  "total_anomalies": 5
}
```

**`group_by` 行为**

| `group_by` 值 | `key` 示例 | 说明 |
|---------------|------------|------|
| `table` | `std.std_ar` | 按表名分组 |
| `assignee` | `zhangsan` | 按负责人分组，未分配显示为 `(unassigned)` |
| `severity` | `高` | 按级别分组 |
| `table,severity` | `std.std_ar::高` | 复合 key |
| `assignee,severity` | `zhangsan::中` | 复合 key |

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `schemas/quality.py` | 新增 `root_cause`、`analyzed_at`、`model_used` 字段 |
| `api/schemas/quality.py` | 新增 `RootCauseAnalysisResponse` schema |
| `services/ai_analysis_service.py` | **新建** — AI 分析逻辑（prompt 构造、LLM 调用、结果解析） |
| `services/field_quality_service.py` | 新增 `analyze_anomaly()`、`get_aggregated_anomalies()` 方法；`check_all()` 自动触发分析 |
| `api/routes/quality.py` | 新增 `POST /anomalies/{id}/analyze`、`GET /anomalies/aggregated` 端点 |
| `api/config.py` | 新增 `AIAnalysisConfig` |
| `scripts/phase7c_ddl.sql` | **新建** — DDL（ALTER TABLE） |
| `scripts/init_phase7c.py` | **新建** — 幂等初始化脚本 |
| `templates/reports/quality_report.html.j2` | 新增根因展示区块 |
| `.env.example` | 新增 `QUALITY_AI_*` 环境变量 |
| `tests/unit/test_ai_analysis_service.py` | **新建** — 单元测试 |
| `tests/integration/test_quality_api.py` | 新增聚合视图和根因分析集成测试 |

---

## 依赖关系

- AI 分析服务依赖 Ollama 服务（`services/ai/ollama_service.py`）
- 无跨服务依赖（不引入新的外部依赖）
- 聚合视图仅依赖现有 `field_quality_service`
