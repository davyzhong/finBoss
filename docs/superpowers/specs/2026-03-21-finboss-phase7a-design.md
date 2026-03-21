# FinBoss Phase 7A - 数据质量监控面板

> 版本：v1.2
> 日期：2026-03-21
> 状态：已评审
> Changelog:
> - v1.1: 初稿
> - v1.2: 补充 SeverityEnum 定义、resolved_at 填充逻辑、API severity 字段说明、实施顺序细化

---

## 一、目标概述

自动发现 ClickHouse 所有用户表，对每个表的每个字段计算质量指标，发现异常后记录数据库并推送飞书卡片。

**核心价值**：
- 字段级精准定位数据问题，不遗漏任何列
- 每日定时扫描，异常早发现、早处理
- 管理层通过飞书卡片实时掌握数据健康度

---

## 二、技术方案

### 2.1 技术栈

- **表发现**：`system.tables` 元数据查询（无需手动配置表）
- **质量计算**：ClickHouse SQL 聚合函数（`countIf / count / uniqExact`）
- **报告生成**：Jinja2 HTML 模板
- **调度**：APScheduler（复用 Phase 5 已引入）
- **飞书推送**：复用 `FeishuClient`

### 2.2 组件复用

| 组件 | 文件 | 调用方式 |
|------|------|---------|
| ClickHouseDataService | `services/clickhouse_service.py` | 查询 system.tables + 质量 SQL |
| FeishuClient | `services/feishu/feishu_client.py` | `send_card_to_channel()` |
| APScheduler | `services/scheduler_service.py` | 新增 `phase7a_daily_quality` job |
| QualityService | `services/quality_service.py` | 扩展 Phase 1 已有的 QualityService |

### 2.3 模块结构

```
schemas/
  └── quality.py                    # QualityReport, QualityAnomaly, Severity

services/
  ├── quality_service.py            # 扩展：新增字段级检查方法
  └── quality_scheduler.py          # APScheduler job 封装（单文件）

api/routes/
  └── quality.py                    # 质量报告 / 异常 / 手动触发 API

templates/reports/
  └── quality_report.html.j2        # 质量报告 HTML 看板

scripts/
  └── phase7a_ddl.sql              # ClickHouse DDL

tests/
  ├── unit/test_quality_service.py  # 扩展字段级检查测试
  └── integration/test_quality_api.py
```

---

## 三、数据模型

### 3.1 `dm.quality_reports` — 质量报告记录

```sql
CREATE TABLE dm.quality_reports (
    id              String,
    stat_date       Date,
    table_name      String,
    total_fields    UInt32,
    anomaly_count   UInt32,
    score_pct       Float64,        -- 正常字段 / 总字段 × 100
    generated_at    DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (stat_date, table_name)
SETTINGS allow_experimental_object_type = 1;
```

### 3.2 `dm.quality_anomalies` — 字段级异常明细

```sql
CREATE TABLE dm.quality_anomalies (
    id              String,
    report_id       String,
    stat_date       Date,
    table_name      String,
    column_name     String,
    metric          String,          -- null_rate / distinct_rate / negative_rate / freshness_hours
    value           Float64,
    threshold       Float64,
    severity        String,          -- 高 / 中 / 低
    status          String,          -- open / resolved / ignored
    detected_at     DateTime,
    resolved_at     DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(detected_at)
ORDER BY (stat_date, table_name, column_name, metric)
SETTINGS allow_experimental_object_type = 1;
```

### 3.3 异常指标定义

```python
class Severity(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"
```

| 指标 | SQL 计算方式 | 高危阈值 | 中危阈值 | 对应 severity |
|------|------------|---------|---------|-------------|
| `null_rate` | `countIf(col IS NULL) / count()` | > 20% | > 10% | 高 / 中 |
| `distinct_rate` | `uniqExact(col) / count()` | > 99.9% | > 99% | 中 / 低 |
| `negative_rate` | `countIf(val < 0) / count()`（仅数值型字段） | > 5% | > 2% | 高 / 中 |
| `freshness_hours` | `now() - MAX(etl_time)` | > 72h | > 48h | 中 / 低 |

**字段类型判断**：通过 `system.columns` 的 `type` 字段识别。
- 数值型：`Int*/UInt*/Float*` → 检查 `negative_rate`
- 可空型：任意类型 → 检查 `null_rate`
- 所有类型 → 检查 `distinct_rate` + `freshness_hours`（若有 `etl_time` 列）

---

## 四、质量检查逻辑

### 4.1 表自动发现

```python
def list_monitored_tables() -> list[str]:
    # 仅扫描用户数据表，排除 system / tmp / 临时表
    sql = """
    SELECT database, name
    FROM system.tables
    WHERE database IN ('raw', 'std', 'dm')
      AND name NOT LIKE '%\_tmp'
      AND engine NOT LIKE '%Temp%'
    ORDER BY database, name
    """
    return [f"{db}.{name}" for db, name in rows]
```

### 4.2 每日检查流程

```
APScheduler: 每日 06:00
    │
    ▼
QualityService.check_all()
    │
    ├── list_monitored_tables() → 所有 dm/std/raw 用户表
    │
    ├── 对每张表：
    │   ├── 获取字段列表（system.columns）
    │   ├── 对每字段构造质量 SQL
    │   ├── 执行查询，获取各指标值
    │   └── 比对阈值，标记 severity
    │
    ▼
    生成 quality_report + quality_anomalies 记录
    │
    ▼
QualityService.send_feishu_card(anomalies)
    │
    ├── 按 severity 分组（高/中/低）
    ├── 构建飞书卡片
    └── send_card_to_channel(card, FEISHU_MGMT_CHANNEL_ID)
```

### 4.3 质量评分

```
score_pct = (正常字段数 / 总字段数) × 100

正常字段定义：所有指标均未超过中危阈值
高危字段：任意一个指标超过高危阈值
```

---

## 五、API 端点

### 5.1 端点总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/quality/reports` | 质量报告列表（分页） |
| GET | `/api/v1/quality/reports/{id}` | 报告详情（含异常明细） |
| GET | `/api/v1/quality/anomalies` | 当前 open 异常列表 |
| PUT | `/api/v1/quality/anomalies/{id}` | 标记已处理 / 忽略 |
| POST | `/api/v1/quality/check` | 手动触发一次检查 |
| GET | `/api/v1/quality/summary` | 全局健康度概览 |

### 5.2 响应模型

**`GET /api/v1/quality/summary` 响应**：
```json
{
  "stat_date": "2026-03-21",
  "total_tables": 12,
  "total_fields": 58,
  "anomaly_count": 3,
  "high_severity": 1,
  "medium_severity": 2,
  "score_pct": 94.8,
  "last_check_at": "2026-03-21T06:00:00"
}
```

> `high_severity` / `medium_severity` 为计数（整数），severity 实际存储值为 `"高"` / `"中"` / `"低"`（`Severity` 枚举）。
```

**`PUT /api/v1/quality/anomalies/{id}` 请求**：
```json
{
  "status": "resolved" | "ignored",
  "note": "已修复，字段已补值"
}
```

> `status=resolved` 时，`QualityService.update_anomaly()` 同步写入 `resolved_at = now()`（UTC）。`status=ignored` 时 `resolved_at` 保持不变。

---

## 六、飞书卡片格式

标题：`🚨 数据质量日报 - {stat_date}`

内容：
- 总览行：`监控 {N} 张表 / {M} 个字段 | ⚠️ 异常 {X} 个（高危 {h} / 中危 {m}） | 健康度 {score}%`
- 高危列表（若存在）
- 中危列表（若存在）
- 底部按钮：`查看看板` → `/static/reports/quality_report_{date}.html`

---

## 七、环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FEISHU_MGMT_CHANNEL_ID` | 管理飞书群 ID | — |
| `QUALITY_CHECK_CRON` | 调度时间 | `0 6 * * *`（每日06:00） |

---

## 八、错误处理

- **ClickHouse 查询失败**：记录 error 日志，跳过当前表，继续检查其他表
- **飞书推送失败**：记录 `sent=0` 状态，不阻塞报告生成
- **表无字段**：跳过该表，不产生报告记录
- **字段类型无法识别**：跳过该字段，不报错

---

## 九、测试策略

- **单元测试**：`QualityService` 质量指标计算逻辑（mock ClickHouse 结果集）
- **单元测试**：阈值比对、severity 判定逻辑
- **集成测试**：API 端点（mock 所有服务层）

---

## 十、实施顺序

```
Step 1: DDL（quality_reports / quality_anomalies）
Step 2: QualityService 字段级检查逻辑 + SeverityEnum + resolved_at 填充
Step 3: Quality API 端点（含 PUT 异常更新逻辑）
Step 4: 质量报告 HTML 看板模板 → static/reports/quality_report_{date}.html
Step 5: APScheduler 06:00 调度集成 + 飞书卡片推送
Step 6: 集成测试
```
