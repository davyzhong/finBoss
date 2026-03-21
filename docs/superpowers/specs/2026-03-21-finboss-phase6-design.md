# FinBoss Phase 6 - 业务员通道 + AP 扩展

> 版本：v1.1
> 日期：2026-03-21
> 状态：待评审
> Changelog:
> - v1.1: 修复评审问题：DDL SETTINGS 一致性、文件大小限制、ClickHouse execute 参数写法、dedup key 修正、UNIQUE 约束、supplier 匹配算法、列名映射优先级、due_date 环境变量化、report_records schema 扩展、filename 净化

---

## 一、目标概述

Phase 6 在 Phase 5 基础上完成两件事：

1. **业务员 AR 报告通道** — 赋能每个业务员看到自己客户的 AR 健康度
2. **AP 扩展（银行对账单）** — 将银行付款记录作为 AP 数据源，构建应付分析

**核心价值**：
- 业务员主动管理自己客户的回款，降低管理成本
- AP 可视化：财务实时掌握付款义务履行情况
- 统一平台覆盖 AR + AP 双视角

---

## 二、技术方案

### 2.1 技术栈

- **AP 数据源**：银行 CSV/Excel 对账单上传
- **报告生成**：复用 Jinja2 模板 + `ReportService` 模式
- **飞书推送**：复用 `FeishuClient`
- **调度**：复用 APScheduler（Phase 5 已引入）

### 2.2 组件复用

| 组件 | Phase 5 文件 | Phase 6 调用方式 |
|------|-------------|----------------|
| ClickHouseDataService | `services/clickhouse_service.py` | 直接实例化 |
| FeishuClient | `services/feishu/feishu_client.py` | 发送飞书卡片 |
| APScheduler | `services/scheduler_service.py` | 新增 AP 每日对账任务 |
| ReportService | `services/report_service.py` | 扩展 generate() 支持 rep_scope |

### 2.3 模块结构

```
schemas/
  └── ap.py                      # APStdRecord, APSupplier Pydantic 模型

services/
  ├── ap_bank_parser.py          # 银行对账单 CSV/Excel 解析
  ├── ap_service.py              # AP 数据聚合服务
  ├── salesperson_mapping_service.py  # 业务员映射 CRUD + CSV 上传
  └── report_service.py          # +per_reports +ap_reports

api/routes/
  ├── ap.py                      # AP 上传 + 查询 + 报告 API
  ├── salesperson_mapping.py      # 业务员映射 CRUD + CSV 上传
  └── reports.py                 # +per-rep 报告触发

api/schemas/
  ├── ap.py                      # API 请求/响应模型
  └── salesperson_mapping.py     # 业务员映射请求/响应模型

scripts/
  ├── phase6_ddl.sql            # ClickHouse DDL（ap_std, supplier_mapping, salesperson_mapping）
  └── init_phase6.py             # Phase 6 表初始化

templates/reports/
  ├── ar_per_salesperson.html.j2  # 业务员 AR 报告模板
  └── ap_report.html.j2           # AP 报告模板

tests/
  ├── unit/test_ap_bank_parser.py
  ├── unit/test_salesperson_mapping_service.py
  └── integration/test_ap_api.py
```

---

## 三、业务员 AR 报告通道

### 3.1 业务员映射数据模型

**`dm.salesperson_mapping`** 和 **`dm.salesperson_customer_mapping`** 表结构和去重策略见 **4.1 节**。

**格式约束**：`salesperson_id` 仅允许大写字母 + 数字（正则 `[A-Z0-9]+`），上传时验证，不符合格式的行拒绝并返回错误。

**Upsert 语义**：CSV 批量上传时使用 `ReplacingMergeTree` 去重，以 `(salesperson_id, customer_id)` 为主键；同一映射重复上传时自动覆盖旧记录，不产生重复行。

### 3.2 业务员映射 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/salesperson/mappings` | 列出所有映射 |
| POST | `/api/v1/salesperson/mappings` | 单条创建 |
| PUT | `/api/v1/salesperson/mappings/{id}` | 更新映射 |
| DELETE | `/api/v1/salesperson/mappings/{id}` | 删除映射 |
| POST | `/api/v1/salesperson/mappings/upload` | CSV 批量上传 |
| GET | `/api/v1/salesperson/{salesperson_id}/customers` | 查询业务员负责的客户 |

**CSV 格式**（批量上传）：
```csv
salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name
S001,张三分,oc_xxxxx,C001,腾讯科技
S001,张三分,oc_xxxxx,C002,阿里巴巴
S002,李四,oc_yyyyy,C003,字节跳动
```

### 3.3 业务员 AR 报告内容

每个业务员的 AR 报告包含：
- 业务员姓名 + 报告日期
- 所负责客户汇总：客户数、AR 总额、逾期总额、逾期率
- **所负责客户明细表格**：客户名 | AR总额 | 逾期金额 | 逾期率 | 风险等级
- **本周/本月新增加逾期客户**（JOIN `alert_history`）
- 底部按钮：查看完整看板

### 3.4 报告触发时机

| 触发方式 | 时间 | 逻辑 |
|---------|------|------|
| APScheduler | 每周一 08:05 | 对每个启用的 `salesperson_id` 生成报告并发送到销售群 |
| APScheduler | 每月1日 08:05 | 同上，周期改为月报 |
| API 手动 | - | `POST /api/v1/reports/ar/per-salesperson` 对指定业务员生成报告 |

### 3.5 飞书发送

发送到**销售团队共享飞书群**（环境变量 `FEISHU_SALES_CHANNEL_ID`）。

---

## 四、AP 扩展（银行对账单）

### 4.1 AP 数据模型

**`raw.ap_bank_statement`** — 原始银行对账单（CSV/Excel 上传）：

> **去重策略**：以 `(file_name, bank_date, transaction_no)` 为主键，同一文件同一日期同一流水号的记录在 `ReplacingMergeTree(created_at)` 下保留最新 `created_at` 的版本。重新上传同一文件时自动覆盖已有记录。

```sql
CREATE TABLE raw.ap_bank_statement (
    id              String,
    file_name       String,          -- 上传文件名（存储前经过 sanitize_filename() 净化）
    bank_date       Date,            -- 交易日期
    transaction_no  String,         -- 流水号（全局唯一，相同流水号 = 同一笔交易）
    counterparty    String,         -- 对方账户名
    amount          Decimal(18,2),  -- 付款金额（正值）
    direction       String,         -- IN / OUT（本系统只处理 OUT = 付款）
    remark          String,         -- 摘要
    created_at      DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (file_name, bank_date, transaction_no)
SETTINGS allow_experimental_object_type = 1;
```

**`std.ap_std_record`** — 标准化 AP 记录（由 `raw.ap_bank_statement` 转换而来）：

> **去重策略**：以 `bank_transaction_no`（即原始流水号）为主键，保证同一笔银行流水不重复写入。`ORDER BY (bank_transaction_no)` 确保唯一性。若流水号为空则按 `(supplier_name, bank_date, amount)` 组合去重。

```sql
CREATE TABLE std.ap_std_record (
    id                  String,
    supplier_code       String,             -- 供应商编码（模糊匹配后填充，未匹配为空字符串）
    supplier_name       String,
    bank_date           Date,
    due_date            Date,               -- 默认 bank_date + AP_DEFAULT_PAYMENT_TERM_DAYS（当前 30 天）
    amount              Decimal(18,2),
    received_amount     Decimal(18,2),      -- 核销金额（付款后填充）
    is_settled          UInt8,              -- 0=未结清 1=已结清
    settlement_date     Date,               -- 结清日期（is_settled=1 时填充）
    bank_transaction_no String,              -- 银行流水号（去重主键）
    payment_method      String,             -- 银行转账 / 支票 / 承兑汇票
    source_file        String,             -- 来源文件名（净化后）
    etl_time            DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(etl_time)
ORDER BY (bank_transaction_no)
SETTINGS allow_experimental_object_type = 1;
```

**`dm.salesperson_mapping`** — 业务员主表：

```sql
CREATE TABLE dm.salesperson_mapping (
    id              String,
    salesperson_id  String,
    salesperson_name String,
    feishu_open_id  String,
    enabled         UInt8,
    created_at      DateTime,
    updated_at      DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (salesperson_id, updated_at)
SETTINGS allow_experimental_object_type = 1;
```

**`dm.salesperson_customer_mapping`** — 客户→业务员多对多映射：

> **去重策略**：`UNIQUE (salesperson_id, customer_id)` 确保同一业务员同一客户不会重复映射。ReplacingMergeTree 以 `created_at` 为版本列，重新上传时覆盖旧记录。

```sql
CREATE TABLE dm.salesperson_customer_mapping (
    id              String,
    salesperson_id  String,
    customer_id     String,
    customer_name   String,
    created_at      DateTime,
    UNIQUE (salesperson_id, customer_id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (salesperson_id, customer_id)
SETTINGS allow_experimental_object_type = 1;
```

**说明**：
- `due_date` 默认付款期限天数由环境变量 `AP_DEFAULT_PAYMENT_TERM_DAYS` 控制（默认 30），ETL 逻辑中读取配置计算。
- 后续若引入供应商付款条款表，可按 `supplier_code` 覆盖默认期限。

### 4.2 银行对账单上传 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/ap/upload` | 上传银行对账单 CSV/Excel |
| GET | `/api/v1/ap/records` | 查询 AP 明细 |
| GET | `/api/v1/ap/suppliers` | 供应商汇总 |
| GET | `/api/v1/ap/kpi` | AP 汇总 KPI |

**上传请求**：`multipart/form-data`，字段名 `file`（支持 .csv / .xlsx）

**安全约束**：
- 文件大小上限：**10 MB**。超过则返回 HTTP 413。前端据此显示错误。
- `file_name` 存储前经 `sanitize_filename()` 净化：剥离路径组件（`/`、`\`、`..`），仅保留字母/数字/`.`/`-`/`_`，截断至 255 字符。

上传后自动：
1. 净化文件名
2. 解析文件，规范化字段名映射
3. 写入 `raw.ap_bank_statement`
4. 转换为 `std.ap_std_record`
5. 返回解析结果（成功行数 / 失败行数 / 错误行详情）

**字段映射**（银行 CSV 常见列名自动识别，**按优先级逐一匹配**）：

> **优先级规则**：同一列名可能匹配多个字段时，按下表从上到下取第一个匹配；同一字段可能在多列中匹配到时，取列名完全包含关键词的那列。

| 目标字段 | 识别规则（按优先级） |
|---------|------------------|
| `bank_date` | 1. 列名含"交易日期" 2. 列名含"记账日期" 3. 列名含"日期" |
| `counterparty` | 1. 列名含"收款人" 2. 列名含"对方账户" 3. 列名含"对方" |
| `amount` | 1. 列名含"金额" 2. 列名含"付款额" |
| `transaction_no` | 1. 列名含"流水号" 2. 列名含"交易流水" 3. 列名含"编号" |
| `remark` | 1. 列名含"摘要" 2. 列名含"用途" |

**供应商模糊匹配算法**（`APBankStatementParser.transform_to_std()` 中）：
1. **精确匹配**：若 `supplier_name` 精确等于已有供应商名称 → 直接使用
2. **去括号匹配**：去除括号内容后精确匹配已有供应商
3. **模糊匹配**：若未命中，使用 `difflib.SequenceMatcher` 计算相似度，超过阈值 0.85 的取最高分者
4. **未匹配**：写入 `supplier_code=''`，在 AP 看板中显示为"未知供应商"，供人工后续映射

**错误行处理**：解析失败的行（类型错误、必填字段缺失）记录到错误列表并跳过，整行不入库；返回响应包含 `errors: [{row: n, reason: "..."}]`。

### 4.3 AP 预警规则

| 规则名称 | 指标 | 条件 | 阈值 | 级别 |
|---------|------|------|------|------|
| 单供应商逾期金额超标 | overdue_amount | > | 500000 | 高 |
| 逾期付款笔数周环比增加 | new_overdue_count | > | 3 | 中 |

### 4.4 AP 看板

在 `DashboardService` 增加 AP 维度数据：

- AP 总额（未结清 + 已结清）
- 未结清金额
- 逾期金额（`is_settled = 0 AND due_date < today()`）
- 逾期率
- 供应商集中度 Top 10
- 逾期分布（账龄分桶）

---

## 五、API 端点总览

### 5.1 业务员映射

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/salesperson/mappings` | 列出所有映射 |
| POST | `/api/v1/salesperson/mappings` | 创建映射 |
| PUT | `/api/v1/salesperson/mappings/{id}` | 更新映射 |
| DELETE | `/api/v1/salesperson/mappings/{id}` | 删除映射 |
| POST | `/api/v1/salesperson/mappings/upload` | CSV 批量上传 |
| GET | `/api/v1/salesperson/{salesperson_id}/customers` | 查询业务员的客户 |

### 5.2 AP 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/ap/upload` | 上传银行对账单 |
| GET | `/api/v1/ap/records` | AP 明细查询 |
| GET | `/api/v1/ap/suppliers` | 供应商汇总 |
| GET | `/api/v1/ap/kpi` | AP 汇总 KPI |
| GET | `/api/v1/ap/dashboard` | AP 看板 HTML |

### 5.3 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/reports/ar/per-salesperson` | 生成业务员 AR 报告（支持指定 salesperson_id 或批量） |
| POST | `/api/v1/reports/ap` | 生成 AP 报告 |
| GET | `/api/v1/reports/records` | 查询发送记录（含 AP 和 per-rep） |

**`POST /api/v1/reports/ar/per-salesperson` 请求体**：
```json
{
  "salesperson_id": "S001",     // 可选，不填则对所有启用的业务员生成
  "report_period": "weekly"     // weekly | monthly
}
```

**响应**：
```json
{
  "status": "generated",
  "files": ["/static/reports/ar_per_salesperson_S001_2026-03-21.html"],
  "count": 1
}
```

---

## 六、数据流

> **ClickHouse INSERT 注意**：`ClickHouseDataService.execute()` 仅接受 `sql: str` 参数，不支持 named params。因此所有 INSERT 语句必须内联拼接值（实施时需注意 SQL 注入风险：所有用户输入值必须经过 `escape_clickhouse_string()` 转义后方可内联）。

```
APScheduler: 每周一 08:05
    │
    ▼
SalespersonMappingService.list_active_salespersons()
    │
    ├── 对每个 salesperson_id:
    │   ├── 获取所负责客户列表（JOIN salesperson_customer_mapping）
    │   ├── 查询每个客户的 AR 数据（dm_customer360）
    │   ├── 聚合为 per-rep AR 报告数据
    │   ├── 填充 ar_per_salesperson.html.j2 模板
    │   └── 发送飞书卡片到销售群
    │
    ▼
记录 report_records（type='ar_per_salesperson', recipients=salesperson_id）

> **report_records 表扩展**：现有 `dm.report_records`（Phase 5）需增加两列以支持 Phase 6：
> - `salesperson_id String Nullable`：per-rep 报告对应的业务员 ID
> - `supplier_code String Nullable`：AP 报告对应的供应商编码（可选，用于 AP 报告筛选）
> DDL 变更在 Phase 6 DDL 脚本中体现。
```

### 6.2 AP 数据流

```
财务上传银行对账单 CSV
    │
    ▼
sanitize_filename(file.name) → 净化文件名
    │
    ▼
APBankStatementParser.parse(file)
    │
    ├── 按优先级规则识别列名映射
    ├── 过滤 direction='IN'（只处理付款=OUT）
    ├── 解析 amount 为 Decimal
    ├── 解析 bank_date 为 Date
    └── 返回 list[BankStatementRecord] 或错误行列表
    │
    ▼
APBankStatementParser.save_raw(records)
    │
    └── INSERT INTO raw.ap_bank_statement
    │
    ▼
APBankStatementParser.transform_to_std(raw_records)
    │
    ├── 对每条记录匹配供应商:
    │   1. 精确匹配已有 supplier_name
    │   2. 去括号后精确匹配
    │   3. difflib similarity > 0.85 取最高分
    │   4. 未匹配 → supplier_code=''
    ├── 计算 due_date = bank_date + AP_DEFAULT_PAYMENT_TERM_DAYS
    └── INSERT INTO std.ap_std_record
    │
    ▼
返回解析结果（含 errors 列表）
```

---

## 七、环境变量

| 变量 | 说明 |
|------|------|
| `FEISHU_SALES_CHANNEL_ID` | 销售团队飞书群 ID |
| `AP_DEFAULT_PAYMENT_TERM_DAYS` | AP 付款期限天数（默认 30） |

---

## 八、错误处理

- **文件超过 10 MB**：返回 HTTP 413，拒绝上传
- **CSV 解析失败**：返回错误行数和原因，跳过失败行继续处理成功行
- **未知列名**：记录警告日志，返回支持识别的列名列表
- **AP 预警飞书推送失败**：记录 error 状态，不阻塞报告生成
- **业务员映射缺失**：`salesperson_id` 在 `salesperson_customer_mapping` 中无匹配客户 → 该业务员报告为空，跳过发送
- **`salesperson_id` 格式校验**：不符合 `[A-Z0-9]+` 的行拒绝并返回错误

---

## 九、测试策略

- **单元测试**：`APBankStatementParser` 列名识别 + 字段映射
- **单元测试**：`SalespersonMappingService` CRUD + CSV 上传解析
- **集成测试**：API 端点（mock 所有服务层）
- **端到端**：上传真实银行对账单 CSV，验证数据落入 `std.ap_std_record`

---

## 十、实施顺序

```
Step 1: DDL（ap_bank_statement / ap_std_record / salesperson_mapping 表）
Step 2: SalespersonMappingService + 映射 API + CSV 上传
Step 3: APBankStatementParser 解析服务
Step 4: AP 上传 API + std 写入
Step 5: AP 看板数据（APAggregatorService + 模板）
Step 6: 业务员 AR 报告服务 + 模板
Step 7: APScheduler 08:05 任务集成
Step 8: 集成测试 + 冒烟测试
```
