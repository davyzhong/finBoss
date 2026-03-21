# FinBoss Phase 5 - 预警报表与自动化报告

> 版本：v1.0
> 日期：2026-03-21
> 状态：草稿

---

## 一、目标概述

Phase 5 在 Phase 4B 客户360基础上，增加三个功能模块：

1. **逾期预警** — 基于规则的实时报警，推送飞书卡片
2. **HTML 看版** — 静态管理看板页面，托管于 FastAPI 静态文件服务
3. **自动化报告** — 每周+每月定时生成并推送（管理层+业务员双通道）

**核心价值**：
- 逾期风险早发现、早介入
- 管理层随时可看 AR 健康度看板
- 自动化报告替代手工报表，减少财务团队重复劳动

---

## 二、技术方案

### 2.1 技术栈

- **报告生成**：Jinja2 模板（`templates/reports/`）
- **静态托管**：FastAPI `StaticFiles` 挂载 `/static/reports/`
- **调度**：`apscheduler`（已引入 Phase 4B）
- **飞书卡片**：复用 `FeishuClient`
- **数据查询**：复用 `ClickHouseDataService`

无新增基础设施依赖。

### 2.2 模块结构

```
api/routes/
  ├── alerts.py       # 预警规则 CRUD + 触发历史查询
  └── reports.py      # 报告生成触发 + 下载 + 发送记录

services/
  ├── alert_service.py       # 预警规则引擎
  ├── report_service.py      # HTML 报告生成 + 发送
  └── dashboard_service.py   # 看版页面生成

schemas/
  └── alert.py        # AlertRule, AlertHistory, AlertLevel

scripts/
  └── generate_dashboard.py   # 看版生成脚本（CLI）

templates/
  └── reports/
      ├── weekly_report.html.j2   # 周报模板
      ├── monthly_report.html.j2  # 月报模板
      └── dashboard.html.j2       # 看版模板

scripts/
  └── phase5_ddl.sql   # ClickHouse 表：alert_rules, alert_history, report_records
```

---

## 三、逾期预警（Alert Service）

### 3.1 预警规则模型

```python
class AlertRule(BaseModel):
    id: str                          # UUID
    name: str                        # 规则名称，如"逾期率超标"
    metric: str                      # 指标名：overdue_rate / overdue_amount / aging_bucket
    operator: str                    # 比较符：gt / lt / gte / lte
    threshold: float                 # 阈值
    scope_type: str                  # 范围：company / customer / sales
    scope_value: str | None          # 具体值，如"腾讯科技"或" salesperson_id"
    alert_level: str                 # 级别：高 / 中 / 低
    enabled: bool                    # 是否启用
    created_at: datetime
    updated_at: datetime
```

### 3.2 内置预警规则

系统初始化时预置以下规则（可通过 API 禁用）：

| 规则名称 | 指标 | 条件 | 阈值 | 级别 |
|---------|------|------|------|------|
| 客户逾期率超标 | overdue_rate | > | 0.3 | 高 |
| 单客户逾期金额超标 | overdue_amount | > | 1000000 | 高 |
| 逾期率月环比恶化 | overdue_rate_delta | > | 0.1 | 中 |
| 新增逾期客户 | new_overdue_count | > | 5 | 中 |
| 账龄超90天占比高 | aging_90pct | > | 0.2 | 高 |

### 3.3 调度逻辑（每日 09:00）

```
APScheduler.daily_job 09:00
    │
    ▼
AlertService.evaluate_all()
    │
    ├── 读取所有 enabled=True 的 AlertRule
    │
    ├── 对每条规则：
    │   ├── 构造 ClickHouse 查询（从 dm_customer360 等）
    │   ├── 执行查询，比对阈值
    │   └── 命中则记录 AlertHistory
    │
    ▼
AlertService.send_summary(alert_history_list)
    │
    ├── 按级别分组（高/中/低）
    ├── 构建飞书卡片（汇总表）
    └── FeishuClient.send_card() → 飞书运维群
```

### 3.4 飞书卡片格式

卡片包含：
- 标题：`🚨 逾期预警日报 - {日期}`
- 今日概览：高危 N 条 / 中危 N 条 / 低危 N 条
- 详情表格：客户名 | 指标名 | 当前值 | 阈值 | 超标幅度
- 底部按钮：`查看看板` → 跳转 `/static/reports/dashboard.html`

---

## 四、HTML 看版（Dashboard）

### 4.1 页面结构

单页 HTML，包含：
- **顶部 KPI 卡**：AR 总额、逾期总额、逾期率、平均账龄
- **集中度图表**：Top 10 客户占比（SVG 柱状图，无外部依赖）
- **逾期分布**：账龄分桶占比（SVG 饼图）
- **趋势图**：近 12 周逾期率趋势（SVG 折线图）
- **风险客户列表**：逾期率 > 30% 的客户表格

### 4.2 生成时机

- **每日 02:00**（随数据刷新后）：`DashboardService.generate()` → 写入 `static/reports/dashboard_{date}.html`
- **手动触发**：`POST /api/v1/reports/dashboard/generate`
- **访问**：`GET /static/reports/dashboard_latest.html`（软链接指向最新）

### 4.3 渲染方式

所有图表使用内联 SVG，无任何 CDN 依赖，页面完全自包含，可在飞书内置浏览器中正常渲染。

---

## 五、自动化报告（Report Service）

### 5.1 报告类型

| 报告 | 频率 | 发送时间 | 接收人 |
|------|------|---------|--------|
| 周报 | 每周一 | 08:00 | 管理层 + 业务员 |
| 月报 | 每月1日 | 08:00 | 管理层 + 业务员 |

### 5.2 管理层报告内容

- AR 概览（总额/逾期/逾期率）
- 同比/环比变化
- 集中度变化
- 风险客户 TOP 10
- 本周/月新增加逾期客户

### 5.3 业务员报告内容

每个业务员只收到自己负责的客户数据：
- 自己的 AR 总额 / 逾期额 / 逾期率
- 自己负责的逾期客户列表
- 与公司平均对比

业务员识别方式：从 `dm_customer360` 表的 `salesperson` 字段（如有）或从 `raw.raw_customer` 表读取 `contact` 字段对应的业务员 ID。**注意**：若 ERP 中无此字段，报告仅发送管理层版本，业务员通道不启用。

### 5.4 发送流程

```
APScheduler: 周一 08:00 / 每月1日 08:00
    │
    ▼
ReportService.generate_report(type, recipients)
    │
    ├── 填充 Jinja2 模板 → HTML 字符串
    ├── 保存至 static/reports/{type}_{date}.html
    ├── 记录 report_records 表（ID / type / date / recipients）
    │
    ▼
ReportService.send_report(report_id, recipients)
    │
    ├── 查询各 recipients 的飞书 open_id
    ├── 发送飞书消息卡片（报告摘要 + 链接按钮）
    └── 更新 report_records 状态为 sent
```

### 5.5 飞书消息卡片

标题：`📊 {报告类型} - {日期}`
内容：3-5 行关键数字摘要
按钮：`查看完整报告` → `/static/reports/{filename}.html`

---

## 六、数据模型

### 6.1 ClickHouse 表

**`dm.alert_rules`** — 预警规则配置
```sql
CREATE TABLE dm.alert_rules (
    id             String,
    name           String,
    metric         String,
    operator       String,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    alert_level    String,
    enabled        UInt8,
    created_at     DateTime,
    updated_at     DateTime
) ENGINE = ReplacingMergeTree(updated_at)
```

**`dm.alert_history`** — 预警触发历史
```sql
CREATE TABLE dm.alert_history (
    id             String,
    rule_id        String,
    rule_name      String,
    alert_level    String,
    metric         String,
    metric_value   Float64,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    triggered_at   DateTime,
    sent           UInt8
) ENGINE = ReplacingMergeTree(triggered_at)
```

**`dm.report_records`** — 报告发送记录
```sql
CREATE TABLE dm.report_records (
    id             String,
    report_type    String,      -- weekly / monthly
    period_start   Date,
    period_end     Date,
    recipients     String,      -- JSON: [{"type": "management"}, {"type": "sales", "salesperson_id": "xxx"}]
    file_path      String,
    sent_at        DateTime,
    status         String       -- generated / sent / failed
) ENGINE = ReplacingMergeTree(sent_at)
```

---

## 七、API 端点

### 7.1 预警规则

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/alerts/rules` | 列出所有规则 |
| POST | `/api/v1/alerts/rules` | 创建规则 |
| PUT | `/api/v1/alerts/rules/{id}` | 更新规则 |
| DELETE | `/api/v1/alerts/rules/{id}` | 删除规则 |
| GET | `/api/v1/alerts/history` | 查询触发历史 |
| POST | `/api/v1/alerts/trigger` | 手动触发一次评估 |

### 7.2 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/reports/weekly` | 手动触发周报 |
| POST | `/api/v1/reports/monthly` | 手动触发生成月报 |
| GET | `/api/v1/reports/records` | 查询发送记录 |
| POST | `/api/v1/reports/dashboard/generate` | 手动生成看板 |
| GET | `/static/reports/{filename}` | 访问报告页面 |

---

## 八、错误处理

- **ClickHouse 查询失败**：记录日志，跳过当次评估；下次调度重试
- **飞书推送失败**：记录 error 状态到 `alert_history`/`report_records`；不阻塞页面生成
- **报告无人值守**：所有调度任务加 try/except；失败发内部日志告警

---

## 九、测试策略

- **单元测试**：`AlertService.evaluate()` 逻辑（mock ClickHouse）
- **单元测试**：`ReportService.render_template()` 输出
- **集成测试**：API 端点（mock 所有服务层）
- **端到端**：手动运行 `scripts/generate_dashboard.py`，验证 HTML 输出

---

## 十、实施顺序

```
Step 1: DDL + 初始化脚本（alert_rules 预置数据）
Step 2: AlertService 核心逻辑 + APScheduler 集成
Step 3: Alert API CRUD
Step 4: DashboardService + 看版模板
Step 5: ReportService + 报告模板
Step 6: 双通道发送逻辑（管理层 + 业务员）
Step 7: 集成测试 + 冒烟测试
```
