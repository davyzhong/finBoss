# 企业财务AI信息化系统 - 设计文档

> 版本：v1.2
> 日期：2026-03-19
> 状态：草稿（Review修复版）
> Changelog:
> - v1.1: 补充CRM集成、可视化编辑器、数据质量引擎设计
> - v1.2: 修复Spec Review指出的6个CRITICAL + 4个HIGH问题

---

## 一、系统定位与目标

**一句话定位**：面向中大型企业的财务AI数据平台，连接异构ERP系统 → 汇聚/标准化数据 → AI驱动的看板/归因/推送/报告输出。

**核心价值**：
- 打破"数据孤岛"，实现ERP+银行+发票+审批文件的统一接入
- 50%+非结构化数据可被AI理解和加工
- 替代手工报表，AI自动生成和更新财务看板
- 归因分析辅助经营决策
- 实时飞书推送，触达一线业务

---

## 二、整体架构图

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                          财务AI信息化系统 (FinBoss)                              │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                          数据治理与安全层 ★                               │  │
│  │  • 权限/行级安全(RLS)  • 数据脱敏(AES-256)  • 列级血缘追踪  • 审计日志   │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  数据接入层    │   数据湖/仓库层    │  处理加工层   │   AI智能层   │  应用层  │  │
│  │               │                   │              │             │          │  │
│  │  • 金蝶        │  ┌─────────────┐ │  • Flink     │ • RAG知识库  │ • 飞书   │  │
│  │  • 用友        │  │  Iceberg    │ │    (实时)    │ • 本地LLM   │   自建应用│  │
│  │  • Oracle     │  │  (统一Lake)  │ │              │ • 云端API    │          │  │
│  │  • SAP        │  │  原始+标准层  │ │  • dbt       │   (通义/    │ • 智能看板│  │
│  │  • 银行流水    │  └──────┬──────┘ │    (批处理)   │   DeepSeek) │          │  │
│  │  • 发票(OCR)  │         │         │              │             │ • 归因分析│  │
│  │  • 审批文件    │         ▼         │  • 数据集     │ • AI自动     │          │  │
│  │  • CRM        │  ┌─────────────┐ │    (主题封装) │   生成看板   │ • 自动化报告│
│  │               │  │  Doris      │ │              │             │          │  │
│  │  • SeaTunnel │  │ (BI查询/ad-hoc)│ │  • 质量监控  │ • 归因推理   │ • 预警推送│  │
│  │    (CDC)     │  └──────┬──────┘ │              │             │          │  │
│  │               │         │         │              │             │          │  │
│  │               │  ┌──────▼──────┐ │              │             │          │  │
│  │               │  │ ClickHouse  │ │              │             │          │  │
│  │               │  │(高频聚合查询) │ │              │             │          │  │
│  │               │  └─────────────┘ │              │             │          │  │
│  └───────────────┴───────────────────┴──────────────┴─────────────┴──────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
```

**数据流说明**：
```
源系统(ERP/银行/CRM) ──[SeaTunnel CDC]──► Iceberg Lake (原始层)
                                                │
                                    ┌────────────┴────────────┐
                                    ▼                             ▼
                         ┌──────────────────┐        ┌──────────────────┐
                         │  Flink (实时)     │        │   dbt (批处理)    │
                         │  分钟级数据       │        │   复杂业务逻辑    │
                         │  简单转换/过滤    │        │   跨数据集join    │
                         └────────┬─────────┘        └────────┬─────────┘
                                  │                             │
                                  ▼                             ▼
                         ┌──────────────────────────────────────────┐
                         │            Iceberg (标准化层)              │
                         └─────────────────────┬────────────────────┘
                                               │
                              ┌────────────────┴────────────────┐
                              ▼                                 ▼
                     ┌──────────────┐                  ┌──────────────┐
                     │   Doris     │                  │ ClickHouse   │
                     │ BI/ad-hoc   │                  │ 高频聚合查询  │
                     └──────────────┘                  └──────────────┘
```

**OLAP引擎分工**：
- **Doris**：承担BI工具连接(ad-hoc查询)、SQL兼容、跨数据集join
- **ClickHouse**：承担高频指标查询(如资金流水实时聚合)、高基数维度分析

---

## 三、数据接入层设计

### 1. 接入架构

```
                    ┌──────────────────────────────────────┐
                    │         SeaTunnel 数据集成平台          │
                    │  (统一接入层，支持200+数据源)            │
                    └──────────────────┬───────────────────┘
                                       │
         ┌────────────┬───────────────┼───────────────┬────────────┐
         │            │               │               │            │
    ┌────▼────┐  ┌────▼────┐  ┌──────▼──────┐  ┌─────▼─────┐  ┌────▼────┐
    │  金蝶API │  │ 用友API  │  │ Oracle/SAP  │  │  银行直连  │  │  文档类  │
    │         │  │         │  │   (DB Link) │  │  (API/OFX) │  │ (PDF/OCR)│
    └─────────┘  └─────────┘  └─────────────┘  └───────────┘  └─────────┘
```

### 2. 接入策略

| 数据源 | 接入方式 | 实时性 | 说明 |
|--------|----------|--------|------|
| 金蝶 | 金蝶API + 星空数据库直连 | 分钟级 | 凭证、科目、余额、应收应付 |
| 用友 | 用友U8/NC API | 分钟级 | 兼容用友NC系列 |
| Oracle | DB Link + Debezium CDC | 秒级 | Oracle ERP数据库直连 |
| SAP | SAP JCo (BAPI调用) + 标准Extractors (RSA7/BW) | 分钟级 | **详见2.1 SAP集成方案** |
| 银行流水 | 银行开放API/银企直连 | 分钟级 | 资金收支实时同步 |
| 发票 | OCR识别 + 电子发票API | T+1 | 识别后结构化存储 |
| 审批文件 | 飞书/钉钉审批API | 实时 | 非结构化数据入湖 |
| CRM | CRM API + Webhook变更推送 | 分钟级 | **详见2.2 CRM集成方案** |

### 2.1 SAP集成详细方案

**SAP连接方式**：
- **BAPI调用**：通过SAP JCo (Java Connector)调用标准BAPI
  - `BAPI_ACC_DOCUMENT_POST` - 财务凭证
  - `BAPI_COSTCENTER_GETLIST` - 成本中心
  - `RFC_READ_TABLE` - 读取透明表（备选）
- **标准Extractors**：使用SAP BW/ECC标准数据提取器
  - RSA7 - Delta Queue (增量抽取)
  - ROIS - 自定义提取器

**推荐方案**：
```
┌─────────────────────────────────────────────────────────────────┐
│                      SAP集成架构                                  │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  SAP JCo     │    │ BW Extractors│    │  IDoc REST   │     │
│  │ (BAPI调用)   │    │  (RSA7)     │    │  (备选)      │     │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘     │
│         │                   │                                     │
│         └───────────────────┼─────────────────────────────────┘   │
│                             ▼                                       │
│                  ┌─────────────────────┐                           │
│                  │  SeaTunnel SAP      │                           │
│                  │     Connector       │                           │
│                  └─────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

**注意**：不使用DataServices，改用开源SAP JCo + 自定义连接器，降低依赖复杂度。

### 2.2 CRM集成与冲突解决

**CRM-ERP数据一致性策略**：
- **权威数据源原则**：财务数据以ERP为准，CRM仅作为客户维度的补充
- **冲突解决规则**：
  1. 客户基础信息（金蝶编码、名称）→ 以ERP为准
  2. 销售机会、预期收入 → 以CRM为准
  3. 同一客户在两个系统出现 → 使用主数据(MDM)系统做映射，无MDM则以ERP客户编码为主键

**CRM数据同步机制**：
```
┌─────────────────────────────────────────────────────────────────┐
│                    CRM同步架构                                    │
│                                                                  │
│  初始全量同步 ──► CRM API全量拉取 ──► 入Iceberg raw层            │
│       │                                                         │
│       ▼                                                         │
│  增量实时同步 ──► CRM Webhook ──► 变更事件 ──► Flink处理 ──► 更新数据集   │
│       │                                                         │
│       │ (若无Webhook，改用定时API轮询，5分钟间隔)                  │
│       ▼                                                         │
│  数据质量检查 ──► 冲突检测 ──► 日志记录 ──► 人工确认(如有冲突)    │
└─────────────────────────────────────────────────────────────────┘
```

**客户360视图更新SLA**：
- 销售机会变更：15分钟内同步
- 客户主数据变更：T+1同步
- 财务关联数据（AR/AP）：实时

### 3. 数据入湖路径

```
原始数据 ──[SeaTunnel/Flume]──► Iceberg Lake ──[Flink实时]──► Doris/ClickHouse
                                  │                          │
                                  │  (历史全量 + 变更记录)    │  (OLAP查询)
                                  ▼                          ▼
                            历史数据保留                  实时报表
```

**Iceberg作为统一Lake格式**：支持ACID事务、时间旅行查询，方便数据回溯和重处理。

---

## 四、数据加工与标准化层

### 1. 数据集（Dataset）概念

数据集是主题封装的核心单元，按财务业务主题划分：

```
Dataset: 应收主题
├── 来源表：金蝶AR + 用友AR
├── 标准化字段：
│   ├── customer_id（客户ID）
│   ├── amount（金额，本位币）
│   ├── due_date（到期日）
│   ├── overdue_days（逾期天数）
│   └── status（正常/逾期/坏账）
└── 刷新频率：准实时

Dataset: 资金主题
├── 来源表：银行流水 + 金蝶日记账
├── 标准化字段：
│   ├── transaction_date
│   ├── balance（账户余额）
│   ├── inflow/outflow
│   └── account_id（账户ID）
└── 刷新频率：分钟级
```

### 2. Flink/dbt 职责边界

**明确分工原则**：
- **Flink（实时流）**：处理分钟级延迟的简单转换、过滤、数据清洗
- **dbt（批处理）**：处理复杂业务逻辑、跨数据集join、指标计算、数据集聚合

**各司其职**：
```
┌─────────────────────────────────────────────────────────────────────────┐
│                        数据处理分工示意                                   │
│                                                                          │
│  实时数据 (分钟级):                                                      │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐          │
│  │ SeaTunnel│────▶│ Flink   │────▶│ Iceberg │     │         │          │
│  │  CDC    │     │ (过滤/  │     │  std_   │     │         │          │
│  │         │     │  转换)  │     │   xx    │     │         │          │
│  └─────────┘     └─────────┘     └────┬────┘     │         │          │
│                                        │          │         │          │
│                                        └──────────┴─────────┘          │
│                                                  │                      │
│  批处理数据 (T+1):                               ▼                      │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐          │
│  │ Iceberg │◀────│  dbt    │◀────│ 源表    │     │ Doris   │          │
│  │  std_   │     │ (复杂   │     │ join/   │     │ /Click  │          │
│  │   xx    │     │  逻辑)  │     │ 聚合    │     │ -House  │          │
│  └────┬────┘     └─────────┘     └─────────┘     └─────────┘          │
│       │                                                                  │
│       └──────────────────────────────────────────────────────────────▶最终OLAP│
└─────────────────────────────────────────────────────────────────────────┘
```

**转换逻辑复用**：
- 公共基础字段在Iceberg标准化曾统一定义
- Flink只做字段映射，不做业务计算
- dbt基于标准化层做业务指标计算
- 避免同一转换逻辑在两处重复定义

### 3. dbt + 主题数据集

- **dbt-core** 做SQL转换和版本化管理
- 每个Dataset对应一个dbt模型，支持回溯重跑
- 财务专员可通过**dbt documentation**理解数据口径
- 数据集支持被多个报表复用，避免口径不一致

### 4. 数据质量监控

```
异常检测 → 自动告警 → 数据集暂停发布 → 人工确认 → 修复后重新发布
```

- 接入层：字段级完整性校验（金额不能为负、日期格式正确）
- 主题层：业务规则校验（AR账龄>180天标记为逾期）
- 跨源层：一致性校验（金蝶余额 = 银行流水合计）

---

## 五、AI智能层设计

### 1. 混合AI架构

```
                    ┌─────────────────────────────────────┐
                    │           AI 智能层                   │
                    └──────────────────┬──────────────────┘
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                               │
    ┌─────────▼─────────┐                       ┌──────────▼──────────┐
    │   本地 AI 引擎     │                       │    云端 AI API      │
    │                   │                       │                      │
    │ • Ollama          │                       │ • 通义千问 / DeepSeek │
    │ • Qwen-14B/32B  │                       │ • DeepSeek-R1        │
    │   (或DeepSeek-70B)│                      │ • GPT-4 (海外)       │
    │ • 金融领域微调   │                       │                      │
    │                   │                       │                      │
    │ 用途：明细数据    │                       │ 用途：归因分析        │
    │ 分析、本地推理    │                       │ 报告生成、复杂推理    │
    │ (数据不出域)      │                       │                      │
    └─────────┬─────────┘                       └──────────┬──────────┘
              │                                              │
              │            ┌────────────────────────────┐    │
              │            │       AI Orchestrator       │    │
              │            │  (统一调度 + 质量门禁)      │    │
              │            └────────────────────────────┘    │
              │                      │                       │
              └──────────────────────┼───────────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │         RAG 知识库               │
                    │                                  │
                    │ • 财务科目体系                    │
                    │ • 指标计算口径                    │
                    │ • 历史异动归因                    │
                    │ • 报告模板                       │
                    └──────────────────────────────────┘
```

**LLM选型策略**：

| 任务类型 | 本地模型 | 云端模型 | 说明 |
|----------|----------|----------|------|
| 简单查询/报表生成 | Qwen-14B | 通义千问 | 日常看板描述 |
| 复杂归因分析 | DeepSeek-70B | DeepSeek-R1 | 多因素推理 |
| 实时风控预警 | Qwen-7B (快速) | - | 低延迟优先 |

**质量门禁与降级策略**：
```java
public class AIOrchestrator {
    // 质量门禁
    public AIResponse process(AIRequest request) {
        // 1. 先尝试本地LLM
        LocalLLMResponse localResponse = localLLM.infer(request);

        // 2. 检查质量门禁
        if (localResponse.confidence >= 0.7 && localResponse.complexity <= MEDIUM) {
            return localResponse;  // 本地足够
        }

        // 3. 复杂问题升级到云端
        if (localResponse.confidence < 0.7 || localResponse.complexity > MEDIUM) {
            return cloudLLM.infer(request);  // 升级到云端
        }

        // 4. 极高复杂度任务
        if (request.getComplexity() > HIGH) {
            return cloudLLM.inferWithDeepReasoning(request);
        }

        return localResponse;
    }
}
```

### 2. RAG知识库设计

#### 2.1 知识库架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RAG 知识库架构                                    │
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │  知识录入    │───▶│  知识解析    │───▶│  向量化      │            │
│  │  (人工/自动) │    │  (Chunking)  │    │  (Embedding) │            │
│  └──────────────┘    └──────────────┘    └──────┬───────┘            │
│                                                  │                      │
│                                                  ▼                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Milvus 向量数据库                            │  │
│  │                                                                   │  │
│  │  Collection: financial_knowledge                                 │  │
│  │  ├── id: 知识ID                                                  │  │
│  │  ├── content: 原始文本                                           │  │
│  │  ├── embedding: 1536维向量                                       │  │
│  │  ├── metadata: {type, source, version, updated_at}              │  │
│  │  └── status: active | archived                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                  │                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     检索与推理流程                                 │  │
│  │                                                                   │  │
│  │  用户查询 ──▶ Query Embedding ──▶ 混合检索 ──▶ Rerank ──▶ LLM │  │
│  │                                      │                           │  │
│  │                              ┌──────┴──────┐                     │  │
│  │                              │ Dense + Sparse│                    │  │
│  │                              │  混合检索     │                    │  │
│  │                              └──────────────┘                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.2 知识库内容

| 知识类型 | 内容示例 | 用途 | 更新频率 |
|----------|----------|------|----------|
| 科目体系 | 收入确认准则、成本分摊规则 | AI理解财务数据语义 | 月度 |
| 指标口径 | "净利润"定义、EBITDA计算方式 | 保证指标计算一致性 | 月度 |
| 历史归因 | 2024年Q3利润下降15%的归因分析 | AI学习归因逻辑 | 实时 |
| 业务规则 | 逾期账龄分类标准、预算超支阈值 | 辅助判断异动原因 | 季度 |
| 报告模板 | 月报模板、周报结构 | 报告自动生成 | 半年度 |
| 法规政策 | 会计准则、税法条文摘要 | 合规判断 | 按需 |

#### 2.3 Embedding 与检索策略

**Embedding模型**：
- 中文优化模型：**text-embedding-3-large** (1536维) 或 **m3e-base**
- 金融术语增强：可对Embedding做微调

**检索策略：混合检索**：
```java
public class HybridRetrieval {
    // Dense检索 - 语义相似度
    DenseResult denseSearch(String query, int topK);

    // Sparse检索 - 关键词匹配 (BM25)
    SparseResult sparseSearch(String query, int topK);

    // 混合融合
    // score = 0.6 * dense_score + 0.4 * sparse_score
    List<Knowledge> hybridSearch(String query, int topK);

    // Rerank - 使用重排序模型提升精度
    List<Knowledge> rerank(String query, List<Knowledge> candidates);
}
```

**知识版本管理**：
```java
public class KnowledgeVersion {
    String knowledgeId;
    int version;
    String content;
    String contentHash;               // 用于变化检测
    String status;                   // active | archived
    long createdAt;
    long archivedAt;

    // 版本更新时，保留历史版本用于回溯
    // AI归因时使用当时版本的规则
}
```

#### 2.4 知识更新流程

```
知识变更 ──▶ 触发条件 ──▶ 知识管理员审批 ──▶ 新版本入库
     │           │                              │
     │           ▼                              ▼
     │    ┌────────────┐                 ┌────────────┐
     │    │ 自动更新   │                 │ 手动更新    │
     │    │ (指标口径) │                 │ (规则/模板) │
     │    └────────────┘                 └────────────┘
     │
     ▼
知识库版本+1, 旧版本归档
```

### 3. 智能看板生成

**输入**：数据集 + 财务科目 + 时间维度
**输出**：AI自动生成图表 + 自然语言描述

```
AI生成看板流程：

1. 理解请求 → "帮我看看Q4各业务线利润情况"
2. 数据检索 → 从Doris查询相关数据集
3. 图表生成 → 自动选择图表类型（柱状图/折线图）
4. 描述生成 → AI生成"业务线A利润最高，环比增长X%"
5. 异常标注 → 自动标注异动点
6. 发布推送 → 生成飞书卡片，推送给相关人
```

### 4. 归因分析引擎

```
归因分析流程：

异动检测 → 获取异动指标 → 检索RAG知识库 →
  │                              ↓
  │                    调用云端API进行归因推理
  │                              ↓
  └──► 归因结果 → 生成分析报告 → 推送飞书 → 存入知识库（积累）
```

---

## 六、应用层设计

### 1. 飞书自建应用

**功能矩阵**：

| 功能 | 描述 | 入口 |
|------|------|------|
| 看板订阅 | 订阅关心的财务看板 | 机器人 + 应用内 |
| 异动推送 | 北极星指标异动实时推送 | 机器人消息 |
| 自然语言查询 | "本月收入是多少？" | 对话窗口 |
| 报告查看 | 查看AI生成的财务报告 | 应用页面 |
| 预警设置 | 设置阈值，触发飞书通知 | 应用设置 |

### 2. 智能看板

**看板类型**：

```
├── 集团合并看板（CFO视角）
│   ├── 集团总收入/总利润
│   ├── 各子公司贡献占比
│   └── 同比/环比异动标注
│
├── AR/AP管理看板（财务经理视角）
│   ├── 应收账款账龄分布
│   ├── 逾期Top10客户
│   └── 回款预测
│
├── 资金管理看板（资金团队视角）
│   ├── 各银行账户余额
│   ├── 本周到期付款
│   └── 资金预测（未来30天）
│
├── 全面预算看板（预算团队视角）
│   ├── 预算执行率
│   ├── 超预算预警
│   └── 滚动预测
│
└── 税务管理看板（税务团队视角）
    ├── 税负率趋势
    ├── 各税种申报进度
    └── 风险预警
```

### 3. 自动化报告

**报告类型**：

| 报告 | 频率 | 推送方式 |
|------|------|----------|
| 日报 | 每日 | 飞书消息 |
| 周报 | 每周一 | 飞书机器人 + 报告链接 |
| 月报 | 每月1日 | 飞书机器人 + 报告详情 |
| 异动专报 | 实时触发 | 飞书机器人卡片 |

**报告格式**：
- 核心指标卡片（数字 + 趋势箭头）
- 异动分析（AI自动标注原因）
- 明细数据表格（可下钻）
- 数据来源与口径说明（可回溯）

---

## 七、模块与子系统划分

```
┌──────────────────────────────────────────────────────────────┐
│                    系统子模块划分                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  模块一：数据接入平台                                          │
│  ├── ERP接入：金蝶、用友、Oracle、SAP                          │
│  ├── 银行流水接入                                             │
│  ├── 发票/审批文件接入                                         │
│  └── 数据集成引擎（SeaTunnel）                                 │
│                                                              │
│  模块二：数据湖与仓库                                          │
│  ├── Iceberg Lake架构                                        │
│  ├── Doris/ClickHouse OLAP                                    │
│  ├── 数据集管理（主题封装）                                    │
│  └── 数据质量监控                                             │
│                                                              │
│  模块三：数据加工与标准化                                       │
│  ├── dbt数据转换                                              │
│  ├── 实时流处理（Flink）                                       │
│  ├── 财务指标计算引擎                                          │
│  └── 异常数据处理                                             │
│                                                              │
│  模块四：AI智能引擎                                            │
│  ├── 本地LLM（Ollama + Qwen）                                 │
│  ├── 云端API（DeepSeek/通义）                                  │
│  ├── RAG知识库                                                │
│  ├── 自然语言查询                                             │
│  ├── 自动看板生成                                             │
│  └── 异动归因分析                                             │
│                                                              │
│  模块五：应用服务                                              │
│  ├── 飞书自建应用                                             │
│  ├── 智能看板展示                                              │
│  ├── 自动化报告生成                                            │
│  └── 预警规则配置                                             │
│                                                              │
│  模块六：平台基础设施                                          │
│  ├── 多租户权限体系                                           │
│  ├── 数据安全与脱敏                                           │
│  ├── 审计日志                                                 │
│  └── 混合部署支持                                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、平台基础设施

### 6.1 多租户权限体系

#### 6.1.1 租户隔离模型

**隔离策略：行级安全(RLS) + Iceberg分区隔离**

```
┌─────────────────────────────────────────────────────────────────┐
│                    租户隔离架构                                    │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    FinBoss 平台                           │   │
│  │                                                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │   租户A       │  │   租户B       │  │   租户C       │   │   │
│  │  │  (集团客户)   │  │  (中型企业)   │  │  (小型企业)   │   │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │   │
│  │         │                  │                  │            │   │
│  │         └──────────────────┼──────────────────┘            │   │
│  │                            ▼                               │   │
│  │              ┌─────────────────────────┐                   │   │
│  │              │   Iceberg Lake (共享)   │                   │   │
│  │              │   tenant_id + date分区  │                   │   │
│  │              │   RLS策略强制过滤       │                   │   │
│  │              └─────────────────────────┘                   │   │
│  │                            │                               │   │
│  │              ┌─────────────┴─────────────┐                │   │
│  │              ▼                           ▼                 │   │
│  │     ┌──────────────┐           ┌──────────────┐          │   │
│  │     │ Doris        │           │ ClickHouse    │          │   │
│  │     │ (RLS过滤)    │           │ (租户分区)    │          │   │
│  │     └──────────────┘           └──────────────┘          │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**隔离实现**：
1. **Iceberg表分区**：按`tenant_id + partition_date`组合分区
2. **行级安全(RLS)**：每个查询自动注入`tenant_id = current_user.tenant_id`过滤条件
3. **Doris RLS**：通过Session变量实现自动过滤
4. **ClickHouse**：使用tenant_id列分区 + WHERE子句强制过滤

#### 6.1.2 权限模型

```
Tenant (租户)
  └── Org (组织) - 集团/子公司/部门
        └── User (用户)
              ├── Role (角色)
              └── Permission (权限)

角色类型:
  - 系统管理员: 全局管理
  - CFO: 全公司财务数据查看
  - 财务经理: 所管辖子公司数据
  - 分析师: 授权范围内的数据
  - 业务负责人: 自己业务线数据
```

**数据权限配置示例**：
```yaml
# 数据权限配置
data_permissions:
  - user_id: "user_cfo_001"
    role: "CFO"
    dataset_id: "dm_ar"
    row_filters:
      - field: "tenant_id"
        operator: "IN"
        values: ["${user.tenant_ids}"]
      - field: "company_code"
        operator: "IN"
        values: ["${user.managed_companies}"]

  - user_id: "user_biz_001"
    role: "业务负责人"
    dataset_id: "dm_ar"
    row_filters:
      - field: "tenant_id"
        operator: "eq"
        values: ["${user.tenant_id}"]
      - field: "business_unit_code"
        operator: "eq"
        values: ["${user.business_unit_code}"]
```

### 6.2 数据安全与脱敏

#### 6.2.1 加密策略

| 层级 | 方案 | 说明 |
|------|------|------|
| 传输加密 | TLS 1.3 | 全链路HTTPS |
| 存储加密 | AES-256 | Iceberg/Doris/ClickHouse数据文件 |
| 密钥管理 | HashiCorp Vault | 集中密钥管理，支持自动轮换 |
| 敏感字段 | 列级加密 | 工资等高度敏感字段单独加密 |

#### 6.2.2 数据脱敏规则

```java
public enum MaskType {
    FULL_MASK,                         // 全部脱敏 ****
    PARTIAL_MASK,                     // 部分脱敏 138****1234
    HASH,                             // 哈希脱敏 (可逆用于分析)
    DATE_SHIFT,                       // 日期偏移（保持相对关系）
    NULL                              // 直接置空
}

// 脱敏配置示例
public class DataMaskingConfig {
    // 字段级脱敏
    Map<String, MaskType> columnMaskRules = {
        "salary": MaskType.FULL_MASK,           // 工资全脱敏
        "id_card": MaskType.PARTIAL_MASK,      // 身份证部分显示
        "phone": MaskType.PARTIAL_MASK,         // 手机号部分显示
        "bank_account": MaskType.HASH,          // 银行账号哈希
    };

    // 角色级脱敏
    Map<String, List<String>> roleMaskColumns = {
        "analyst": ["salary"],                  // 分析师可看脱敏后工资
        "business_owner": ["salary"],            // 业务负责人仅看汇总
    };
}
```

### 6.3 数据血缘追踪

**追踪粒度：列级血缘**

```
┌─────────────────────────────────────────────────────────────────┐
│                    列级血缘追踪架构                                │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │  Iceberg    │───▶│  DataHub    │───▶│  Doris     │        │
│  │  Table      │    │  (元数据)   │    │  Query     │        │
│  │  Column     │    │             │    │  Lineage    │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│                                                                  │
│  血缘示例：                                                       │
│  dm_ar.total_amount                                             │
│    ├── 来源: std_ar.amount (金蝶AR表)                           │
│    ├── 转换: SUM()聚合                                          │
│    └── 依赖: dm_gl.revenue (总账收入)                           │
└─────────────────────────────────────────────────────────────────┘
```

**血缘API**：
```java
public interface LineageService {
    // 查询列血缘
    List<ColumnLineage> getColumnLineage(String datasetId, String columnName);

    // 查询数据集血缘
    List<DatasetLineage> getDatasetLineage(String datasetId);

    // 影响分析：修改上游影响哪些下游
    List<ImpactAnalysis> analyzeImpact(String datasetId, String columnName);
}
```

### 6.4 审计日志

```java
public class AuditEvent {
    String eventId;
    long timestamp;

    // 操作者
    String userId;
    String userName;
    String tenantId;
    String ipAddress;

    // 操作类型
    AuditAction action;              // QUERY | EXPORT | LOGIN | CONFIG_CHANGE | DATA_ACCESS

    // 资源
    String resourceType;             // dataset | dashboard | report | user | config
    String resourceId;
    String resourceName;

    // SQL查询（如果是数据查询）
    String sqlQuery;

    // 结果
    AuditResult result;             // SUCCESS | FAILURE | PARTIAL
    long durationMs;
    String failureReason;
}

// 审计日志查询API
public interface AuditService {
    PageResult<AuditEvent> queryAuditLogs(AuditQuery query);

    // 合规报表
    AuditReport generateComplianceReport(ComplianceReportRequest request);
}

// 审计日志保留策略
/*
 * - 操作日志: 保留2年
 * - 数据访问日志: 保留1年
 * - 登录日志: 保留2年
 * - 配置变更日志: 永久保留
 */
```

### 6.5 高可用与灾难恢复

**RPO/RTO目标**：

| 数据层 | RPO | RTO | 备份策略 |
|--------|-----|-----|----------|
| Iceberg Lake | 1小时 | 4小时 | 跨可用区3副本 |
| Doris | 1分钟 | 30分钟 | 主从复制 + 定期备份 |
| ClickHouse | 1分钟 | 30分钟 | ReplicatedMergeTree |
| RAG知识库 | 1天 | 4小时 | 每日增量备份 |

**Flink Checkpoint配置**：
```yaml
flink:
  checkpoint:
    interval: 5_minutes          # 每5分钟checkpoint
    timeout: 10_minutes          # checkpoint超时
    external:
      enabled: true
      storage: hdfs://namenode:8020/finboss/checkpoints
      cleanup: RETAINED_WHEN_CANCELLED  # 任务取消保留
```

---

## 八、部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                        企业内网（私有化）                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   金蝶/用友  │  │   Oracle   │  │      SAP            │  │
│  │   (ERP)     │  │   /SAP     │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                    │              │
│  ┌──────▼────────────────▼────────────────────▼──────────┐  │
│  │              SeaTunnel 数据集成节点                      │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                              │                                │
│  ┌──────────────────────────▼─────────────────────────────┐  │
│  │              Iceberg Lake（数据湖）                      │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                              │                                │
│  ┌──────────────────────────▼─────────────────────────────┐  │
│  │         Flink + dbt（流批处理）                        │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                              │                                │
│  ┌──────────────────────────▼─────────────────────────────┐  │
│  │         Doris + ClickHouse（OLAP）                     │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                              │                                │
│  ┌──────────────────────────▼─────────────────────────────┐  │
│  │         Ollama 本地AI推理节点                           │  │
│  │         （财务数据本地处理，不出域）                      │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                                  │
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                        云端（公有云）                         │
│  ┌─────────────────┐  ┌─────────────────────────────────┐   │
│  │   飞书云空间     │  │     云端AI API                   │   │
│  │   (推送服务)     │  │  (DeepSeek / 通义千问 / Claude)   │   │
│  └─────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 九、技术栈选型汇总

| 层级 | 组件 | 选型理由 |
|------|------|----------|
| 数据集成 | SeaTunnel | 国产开源，200+连接器，CDC支持好 |
| 数据湖格式 | Iceberg | ACID事务，时间旅行，跨引擎共享 |
| 实时流处理 | Flink | 成熟稳定，流批一体 |
| 批处理转换 | dbt-core | SQL版本化管理，财务友好 |
| OLAP引擎 | Doris + ClickHouse | Doris兼容MySQL协议，BI友好；ClickHouse高性能查询 |
| 本地LLM | Ollama + Qwen | 本地部署，数据不出域 |
| 云端AI | DeepSeek / 通义千问 | 国产合规能力强 |
| 知识库 | Milvus / QAnything | RAG检索引擎 |
| 协同入口 | 飞书自建应用 | 已有飞书生态，推送+交互合一 |
| 可视化 | Grafana（定制） | 灵活定制财务看板 |

---

## 十、API设计标准

### 10.1 RESTful API规范

#### 10.1.1 URL规范

```
# 版本化URL
/api/v1/datasets
/api/v1/datasets/{id}

/api/v1/dashboards
/api/v1/dashboards/{id}

/api/v1/indicators
/api/v1/indicators/{id}

/api/v1/ai/query
/api/v1/ai/attribution

# 动作使用HTTP方法
GET    /datasets          # 列表
POST   /datasets          # 创建
GET    /datasets/{id}     # 获取
PUT    /datasets/{id}     # 更新
DELETE /datasets/{id}     # 删除
POST   /datasets/{id}/refresh  # 触发刷新

# 嵌套资源
GET /datasets/{id}/columns
GET /datasets/{id}/data
```

#### 10.1.2 错误响应格式

```json
{
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "数据集不存在或无访问权限",
    "details": {
      "dataset_id": "ds_xxx",
      "request_id": "req_yyy"
    },
    "timestamp": "2026-03-19T10:30:00Z"
  }
}
```

**错误码规范**：
| 错误码 | HTTP Status | 说明 |
|--------|-------------|------|
| VALIDATION_ERROR | 400 | 请求参数校验失败 |
| UNAUTHORIZED | 401 | 未认证 |
| FORBIDDEN | 403 | 无权限 |
| NOT_FOUND | 404 | 资源不存在 |
| CONFLICT | 409 | 资源冲突 |
| INTERNAL_ERROR | 500 | 内部错误 |
| SERVICE_UNAVAILABLE | 503 | 服务不可用 |

#### 10.1.3 分页规范

```json
// 请求
GET /datasets?cursor=eyJpZCI6MTIzfQ&limit=20

// 响应
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTQzfQ",
    "has_more": true,
    "total": 156
  }
}
```

#### 10.1.4 限流规范

```
# 限流响应头
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1710835200

# 限流后返回
HTTP/1.1 429 Too Many Requests
Retry-After: 60
```

### 10.2 内部服务通信

**gRPC用于高性能场景**：
```protobuf
service DataSetService {
  rpc GetDataset(GetDatasetRequest) returns (Dataset);
  rpc QueryData(QueryDataRequest) returns (QueryDataResponse);
  rpc StreamData(StreamDataRequest) returns (stream DataRecord);
}
```

**Event Bus用于异步通信**：
```yaml
# Kafka Topic命名规范
finboss.dataset.created
finboss.dataset.refreshed
finboss.alert.triggered
finboss.report.generated
```

---

## 十一、数据接入层补充设计（缺口1：CRM集成）

### 10.1 CRM数据接入架构

原有设计覆盖了ERP、银行、发票、审批，但CRM是重要的客户数据来源，需要补充。

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CRM 数据接入架构                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    SeaTunnel CRM Connector                      │ │
│  │              (统一接入Salesforce/用友CRM/金蝶CRM)                 │ │
│  └────────────────────────────┬───────────────────────────────────┘ │
│                               │                                       │
│  ┌───────────────┬───────────┴───────────────┬───────────────────┐  │
│  │               │                           │                    │  │
│  ┌───▼─────┐  ┌──▼─────┐  ┌──────────▼──┐  ┌──────▼─────┐     │
│  │ Salesforce│  │ 用友CRM │  │  金蝶CRM     │  │  通用HTTP  │     │
│  │ Connector │  │Connector│  │  Connector   │  │  Connector │     │
│  └───────────┘  └─────────┘  └─────────────┘  └────────────┘     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CRM 标准化数据集                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │ std_customer│  │std_opportunity│ std_sales   │                │
│  │  (客户主数据)│  │ (销售机会)   │ (销售数据)  │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                │
│                                                                      │
│  关联现有数据集：                                                    │
│  • std_customer → dm_ar (客户维度)                                   │
│  • std_opportunity → dm_ar (预期收入关联AR)                          │
│  • std_sales → dm_gl (销售收入核对)                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 CRM连接器接口

```java
public interface CrmConnector {
    // 客户主数据
    List<Customer> fetchCustomers(CustomerQuery query);

    // 销售机会/合同
    List<Opportunity> fetchOpportunities(OpportunityQuery query);

    // 销售订单
    List<SalesOrder> fetchSalesOrders(SalesOrderQuery query);

    // 销售目标
    List<SalesTarget> fetchSalesTargets(SalesTargetQuery query);

    // 销售团队
    List<SalesTeam> fetchSalesTeams(SalesTeamQuery query);
}
```

### 10.3 CRM标准化表结构

```sql
-- 客户主数据标准化表
CREATE TABLE iceberg.standardized.std_customer (
    id STRING NOT NULL,
    source_system STRING NOT NULL,        -- 'salesforce' | 'yonyou_crm' | 'kingdee_crm'
    source_id STRING NOT NULL,

    -- 标准字段
    customer_code STRING NOT NULL,        -- 统一客户编码
    customer_name STRING NOT NULL,
    customer_type STRING,                 -- 'enterprise' | 'individual' | 'government'
    industry STRING,                     -- 行业
    region STRING,                       -- 区域
    tier STRING,                         -- 客户分级 A/B/C

    -- 联系信息
    contact_name STRING,
    contact_phone STRING,
    contact_email STRING,

    -- 财务关联
    credit_limit DECIMAL(18,2),          -- 信用额度
    payment_terms STRING,                -- 付款条款

    business_date DATE,
    update_time TIMESTAMP,
    partition_date DATE NOT NULL
)
USING iceberg
PARTITIONED BY (days(partition_date));

-- 销售机会标准化表
CREATE TABLE iceberg.standardized.std_opportunity (
    id STRING NOT NULL,
    source_system STRING NOT NULL,
    source_id STRING NOT NULL,

    opportunity_code STRING NOT NULL,
    opportunity_name STRING NOT NULL,

    -- 关联
    customer_code STRING,
    sales_rep_code STRING,
    sales_team_code STRING,

    -- 金额
    expected_amount DECIMAL(18,2),       -- 预期金额
    probability DECIMAL(5,2),            -- 赢单概率
    weighted_amount DECIMAL(18,2),       -- 加权金额 = expected_amount * probability

    -- 日期
    expected_close_date DATE,
    actual_close_date DATE,

    -- 阶段
    stage STRING,                        -- 'prospecting' | 'qualification' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost'

    business_date DATE,
    partition_date DATE NOT NULL
)
USING iceberg
PARTITIONED BY (days(partition_date));
```

### 10.4 CRM与财务数据关联

CRM数据需要与现有财务数据集关联，形成完整的客户360视图：

```java
// 客户360视图服务
public interface Customer360Service {

    // 获取客户完整视图
    Customer360View getCustomer360(String customerCode);

    // 客户贡献度分析（CRM销售 + 财务AR/AP）
    CustomerContribution getCustomerContribution(String customerCode, DateRange range);

    // 客户风险评估
    CustomerRiskAssessment assessCustomerRisk(String customerCode);
}

public class Customer360View {
    // 基础信息
    Customer customer;

    // 销售信息
    List<Opportunity> activeOpportunities;
    List<SalesOrder> recentOrders;
    Decimal expectedRevenue;              -- 预期收入

    // 财务信息
    Decimal totalReceivable;             -- 应收总额
    Decimal overdueReceivable;           -- 逾期应收
    Decimal payables;                    -- 应付
    Decimal creditUtilization;           -- 信用额度使用率

    // 风险指标
    CustomerRiskLevel riskLevel;         -- A/B/C风险等级
    List<RiskSignal> riskSignals;        -- 风险信号
}
```

---

## 十一、可视化加工层设计（缺口2：面向财务专员的数据集编辑器）

### 11.1 设计背景

原有设计中，dbt面向技术/分析师，但财务专员（非技术背景）需要可视化方式加工数据。补充设计**数据集可视化编辑器（Dataset Studio）**。

### 11.2 数据集编辑器架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Dataset Studio (可视化加工层)                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Web端：数据集编辑器                           │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │ │
│  │  │ 数据源   │  │ 字段映射 │  │  数据预览 │  │  SQL预览 │       │ │
│  │  │ 选择器   │→│  可视化   │→│  实时    │→│  实时   │       │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │ │
│  │       │                                                │        │ │
│  │       └──────────────┬───────────────────────────────┘         │ │
│  │                      ▼                                          │ │
│  │              ┌──────────────┐                                   │ │
│  │              │  dbt Model   │ ← 生成dbt YAML + SQL              │ │
│  │              │  Generator   │                                   │ │
│  │              └──────────────┘                                   │ │
│  └────────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
│                    ┌──────────▼──────────┐                          │
│                    │    dbt-core        │                          │
│                    │  (执行 + 版本管理)   │                          │
│                    └──────────┬──────────┘                          │
│                               │                                       │
│                    ┌──────────▼──────────┐                          │
│                    │   Iceberg / Doris   │                          │
│                    └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.3 数据集编辑器 - Web界面设计

#### 11.3.1 主界面布局

```
┌──────────────────────────────────────────────────────────────────────────┐
│  数据集编辑器                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 面包屑: 首页 / 数据集 / 新建                                         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │  步骤1: 选择数据源            │  │                                 │  │
│  │  ┌───────────────────────┐  │  │  ┌─────────────────────────┐   │  │
│  │  │ 📦 金蝶_AR             │  │  │  │ 字段预览                 │   │  │
│  │  │ 📦 用友_AR             │  │  │  │                         │   │  │
│  │  │ 📦 银行流水             │  │  │  │ customer_id  STRING ✓ │   │  │
│  │  │ 📦 合同系统             │  │  │  │ amount         DECIMAL✓│   │  │
│  │  └───────────────────────┘  │  │  │ due_date       DATE   ✓ │   │  │
│  │                             │  │  │ status         STRING ✓ │   │  │
│  │  已选: [金蝶_AR ×]          │  │  │                         │   │  │
│  │                             │  │  └─────────────────────────┘   │  │
│  └─────────────────────────────┘  └─────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │  步骤2: 字段映射与加工       │  │                                 │  │
│  │  ┌───────────────────────┐  │  │  ┌─────────────────────────┐   │  │
│  │  │ 源字段   → 目标字段   │  │  │  │ 实时预览                │   │  │
│  │  │ ─────────────────────│  │  │  │ ┌─────┬────────┬──────┐│   │  │
│  │  │ cust_id → customer_id│  │  │  │ │customer│ amount │status││   │  │
│  │  │ amt     → amount    │  │  │  │ ├─────┼────────┼──────┤│   │  │
│  │  │ due_dt  → due_date  │  │  │  │ │C001  │158000  │正常  ││   │  │
│  │  │                       │  │  │  │ │C002  │230000  │逾期  ││   │  │
│  │  │ [+ 添加计算字段]       │  │  │  │ └─────┴────────┴──────┘│   │  │
│  │  └───────────────────────┘  │  │  └─────────────────────────┘   │  │
│  └─────────────────────────────┘  └─────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  步骤3: 刷新策略                                                    │  │
│  │  ○ 准实时 (每5分钟)   ○ 小时级   ○ 日级 (T+1)   ○ 自定义           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────┐                                       │
│  │  [预览SQL] [保存草稿] [发布] │                                       │
│  └─────────────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

#### 11.3.2 计算字段定义（可视化）

```
┌──────────────────────────────────────────────────────────────────────────┐
│  添加计算字段                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  字段名称: overdue_days (逾期天数)                                       │
│                                                                          │
│  计算方式:                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  [due_date       ] - [当前日期]  =  [overdue_days]                 │ │
│  │   日期字段            系统函数          结果字段                      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  公式预览:                                                              │
│  │  DATEDIFF(CURRENT_DATE, due_date) AS overdue_days                   │ │
│                                                                          │
│  常用模板:                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │ 逾期天数     │ │ 本位币金额   │ │ 年化金额     │ │ 账龄分段     │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│                                                                          │
│  预览结果:                                                              │
│  ┌─────┬────────┬────────────┬──────────────┐                         │
│  │cust │ amount │ due_date   │ overdue_days │                         │
│  ├─────┼────────┼────────────┼──────────────┤                         │
│  │C001 │158000  │ 2026-03-01 │     18天     │ ← 正常                  │
│  │C002 │230000  │ 2026-02-01 │     46天     │ ← 逾期                  │
│  └─────┴────────┴────────────┴──────────────┘                         │
│                                                                          │
│                              [取消]  [确定添加]                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 11.4 Dataset Studio API

```java
public interface DatasetStudioService {

    // ========== 数据源管理 ==========

    // 获取可用数据源
    List<DataSource> listDataSources();

    // 获取数据源表结构
    List<ColumnMetadata> getTableMetadata(String dataSourceId, String tableName);

    // ========== 数据集编辑 ==========

    // 创建数据集配置
    DatasetConfig createDataset(DatasetConfig config);

    // 更新数据集配置
    void updateDataset(String datasetId, DatasetConfig config);

    // 预览数据集SQL
    String previewSQL(String datasetId);

    // 预览数据集数据
    List<Map<String, Object>> previewData(String datasetId, int limit);

    // ========== 发布管理 ==========

    // 发布数据集（生成dbt模型）
    PublishResult publishDataset(String datasetId);

    // 下线数据集
    void deprecateDataset(String datasetId);

    // 回滚版本
    void rollbackDataset(String datasetId, int version);
}

public class DatasetConfig {
    String name;                          // '应收主题_v1'
    String description;

    // 数据源配置
    List<DataSourceConfig> sources;       // 可以多数据源join

    // 字段映射
    List<FieldMapping> fieldMappings;

    // 计算字段
    List<CalculatedField> calculatedFields;

    // 过滤条件
    List<FilterCondition> filters;

    // 刷新策略
    RefreshStrategy refreshStrategy;

    // 所有者
    String owner;
}

public class DataSourceConfig {
    String sourceId;                     // 'kingdee_ar'
    String tableName;                    // 't_ar_verify'
    List<String> selectedColumns;        // ['cust_id', 'amt', 'due_dt']
    String alias;                        // 'ar'
}

public class FieldMapping {
    String sourceColumn;                 // 'cust_id'
    String targetColumn;                 // 'customer_id'
    String targetType;                  // 'STRING'
    String description;
}

public class CalculatedField {
    String name;                        // 'overdue_days'
    String expression;                  // 'DATEDIFF(CURRENT_DATE, due_date)'
    String resultType;                  // 'INT'
    String description;
}
```

### 11.5 dbt模型生成器

```java
// 将可视化配置转换为dbt模型
public class DbtModelGenerator {

    public DbtModel generate(DatasetConfig config) {
        DbtModel model = new DbtModel();
        model.setName(config.getName().replace(" ", "_").toLowerCase());
        model.setDescription(config.getDescription());

        // 生成SQL
        model.setSql(generateSQL(config));

        // 生成YAML配置
        model.setYaml(generateYaml(config));

        return model;
    }

    private String generateSQL(DatasetConfig config) {
        StringBuilder sql = new StringBuilder();

        // WITH子句 - 源表CTE
        sql.append("WITH source_data AS (\n");
        for (DataSourceConfig source : config.getSources()) {
            sql.append(String.format("    SELECT %s FROM %s AS %s\n",
                String.join(", ", source.getSelectedColumns()),
                source.getTableName(),
                source.getAlias()));
        }
        sql.append("),\n\n");

        // 主查询
        sql.append("SELECT\n");
        for (FieldMapping mapping : config.getFieldMappings()) {
            sql.append(String.format("    %s.%s AS %s,\n",
                getSourceAlias(mapping.getSourceColumn(), config),
                mapping.getSourceColumn(),
                mapping.getTargetColumn()));
        }
        for (CalculatedField calc : config.getCalculatedFields()) {
            sql.append(String.format("    %s AS %s,\n", calc.getExpression(), calc.getName()));
        }
        sql.setLength(sql.length() - 2); // 去掉最后的逗号
        sql.append("\nFROM source_data");

        return sql.toString();
    }
}
```

---

## 十二、数据质量监控设计（缺口3：规则引擎与界面）

### 12.1 数据质量监控架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Data Quality Center (DQC)                          │
│                    数据质量中心 - 规则配置 + 执行 + 报告                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      质量规则配置层                              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │ │
│  │  │ 完整性   │  │ 准确性   │  │ 一致性   │  │ 时效性   │       │ │
│  │  │ 规则     │  │ 规则     │  │ 规则     │  │ 规则     │       │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │ │
│  └────────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
│  ┌────────────────────────────▼─────────────────────────────────────┐ │
│  │                      质量引擎 (DQC Engine)                        │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │  规则执行器  │  异常检测器  │  告警触发器  │  报告生成器   │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
│         ┌─────────────────────┼─────────────────────┐                  │
│         │                     │                     │                  │
│  ┌──────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐         │
│  │ 质量告警    │      │ 阻断发布    │      │ 质量报告    │         │
│  │ (飞书通知)  │      │ (数据阻塞)  │      │ (Dashboard) │         │
│  └─────────────┘      └─────────────┘      └─────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

### 12.2 质量规则模型

```java
// 数据质量规则
public class DataQualityRule {
    String id;

    // 规则基本信息
    String name;                        // 'AR金额不能为负'
    String description;
    String datasetId;                   // 关联数据集
    String targetColumn;                // 目标字段

    // 规则类型
    RuleType type;                      // COMPLETENESS | ACCURACY | CONSISTENCY | TIMELINESS
    RuleSubType subType;               // 规则子类型

    // 触发条件
    String expression;                  // SQL表达式条件

    // 严重级别
    Severity severity;                  // BLOCKING(阻断) | WARNING(警告) | INFO(提示)

    // 告警配置
    AlertConfig alertConfig;

    // 状态
    boolean enabled;
    CronExpression schedule;            // 检查频率
}

// 规则类型枚举
public enum RuleType {
    COMPLETENESS("完整性"),              // 非空、唯一性
    ACCURACY("准确性"),                  // 值域、格式、范围
    CONSISTENCY("一致性"),               // 跨表、跨系统
    TIMELINESS("时效性");                // 数据延迟
}

public enum RuleSubType {
    // 完整性
    NOT_NULL("不能为空"),
    UNIQUE("唯一性"),

    // 准确性
    VALUE_RANGE("值域范围"),
    DATA_FORMAT("数据格式"),
    REGEX_MATCH("正则匹配"),
    REFERENCE_INTEGRITY("参照完整性"),

    // 一致性
    CROSS_TABLE_EQUAL("跨表相等"),
    CROSS_SYSTEM_EQUAL("跨系统相等"),
    BUSINESS_RULE("业务规则"),

    // 时效性
    DATA_FRESHNESS("数据新鲜度"),
    UPDATE_DELAY("更新延迟");
}

// 严重级别
public enum Severity {
    BLOCKING("阻断", true),             // 阻止数据发布
    WARNING("警告", false),             // 发送告警
    INFO("提示", false);                // 仅记录

    boolean blockPublish;
}
```

### 12.3 预置质量规则模板

系统预置常用财务数据质量规则：

```java
public class DataQualityTemplates {

    // ========== 应收(AR)规则 ==========
    public static List<DataQualityRule> getARRules() {
        return Arrays.asList(
            // 完整性规则
            createRule("AR_001", "客户编码不能为空", "dm_ar", "customer_code",
                RuleType.COMPLETENESS, RuleSubType.NOT_NULL, Severity.BLOCKING),

            createRule("AR_002", "金额不能为空", "dm_ar", "total_amount",
                RuleType.COMPLETENESS, RuleSubType.NOT_NULL, Severity.BLOCKING),

            // 准确性规则
            createRule("AR_003", "金额必须大于0", "dm_ar", "total_amount",
                RuleType.ACCURACY, RuleSubType.VALUE_RANGE, "value > 0", Severity.BLOCKING),

            createRule("AR_004", "逾期天数不能为负", "dm_ar", "overdue_days",
                RuleType.ACCURACY, RuleSubType.VALUE_RANGE, "value >= 0", Severity.WARNING),

            createRule("AR_005", "逾期率0-1之间", "dm_ar", "overdue_rate",
                RuleType.ACCURACY, RuleSubType.VALUE_RANGE, "value >= 0 AND value <= 1", Severity.BLOCKING),

            // 一致性规则
            createRule("AR_006", "AR余额=客户维度汇总", "dm_ar", "total_amount",
                RuleType.CONSISTENCY, RuleSubType.CROSS_TABLE_EQUAL,
                "与金蝶AR余额表核对", Severity.BLOCKING),

            // 时效性规则
            createRule("AR_007", "数据延迟不超过5分钟", "dm_ar", "etl_time",
                RuleType.TIMELINESS, RuleSubType.DATA_FRESHNESS, "< 5 MINUTE", Severity.WARNING)
        );
    }

    // ========== 资金(CASH)规则 ==========
    public static List<DataQualityRule> getCashRules() {
        return Arrays.asList(
            createRule("CASH_001", "账户余额不能为空", "dm_cash", "balance",
                RuleType.COMPLETENESS, RuleSubType.NOT_NULL, Severity.BLOCKING),

            createRule("CASH_002", "银行流水收付合计=日记账合计", "dm_cash", "inflow",
                RuleType.CONSISTENCY, RuleSubType.CROSS_TABLE_EQUAL,
                "银行流入=金蝶日记账流入", Severity.BLOCKING),

            createRule("CASH_003", "资金余额不能为负", "dm_cash", "balance",
                RuleType.ACCURACY, RuleSubType.VALUE_RANGE, "value >= 0", Severity.WARNING)
        );
    }

    // ========== 预算(BUDGET)规则 ==========
    public static List<DataQualityRule> getBudgetRules() {
        return Arrays.asList(
            createRule("BUD_001", "预算执行率0-2之间", "dm_budget", "execute_rate",
                RuleType.ACCURACY, RuleSubType.VALUE_RANGE, "value >= 0 AND value <= 2", Severity.WARNING),

            createRule("BUD_002", "超预算必须标记", "dm_budget", "exceed_flag",
                RuleType.BUSINESS_RULE, "execute_rate > 1 AND exceed_flag = false", Severity.BLOCKING)
        );
    }
}
```

### 12.4 质量检查执行

```java
public interface DataQualityService {

    // 执行单条规则检查
    RuleCheckResult checkRule(String ruleId, String datasetId);

    // 执行数据集所有规则
    List<RuleCheckResult> checkDataset(String datasetId);

    // 批量检查（定时任务）
    BatchCheckResult batchCheck(BatchCheckRequest request);

    // 获取质量评分
    QualityScore getQualityScore(String datasetId);

    // 获取质量报告
    QualityReport getQualityReport(QualityReportQuery query);
}

public class RuleCheckResult {
    String ruleId;
    String datasetId;
    CheckStatus status;                  // PASS | FAIL | ERROR

    // 检查详情
    long totalRecords;                  // 总记录数
    long validRecords;                  // 合法记录数
    long invalidRecords;                // 非法记录数
    double passRate;                   // 通过率

    // 失败样本
    List<Map<String, Object>> failedSamples;

    // 执行信息
    long executionTimeMs;
    String executedAt;
    String executedBy;                  // 'system' | userId
}

public enum CheckStatus {
    PASS("通过"),
    FAIL("失败"),
    ERROR("执行错误");
}

// 批量检查请求
public class BatchCheckRequest {
    List<String> datasetIds;            // 检查的数据集
    List<String> ruleIds;               // 检查的规则（为空则检查所有）
    DateRange dateRange;                 // 数据日期范围
    boolean blockingOnly;               // 只检查BLOCKING级别
}
```

### 12.5 质量监控Web界面

```
┌──────────────────────────────────────────────────────────────────────────┐
│  数据质量中心                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [数据集筛选 ▼] [规则类型 ▼] [严重级别 ▼] [搜索...]                       │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  数据集质量概览                                                     │  │
│  │                                                                     │  │
│  │  dm_ar (应收主题)          dm_cash (资金主题)      dm_budget (预算)  │  │
│  │  ┌──────────────────┐     ┌──────────────────┐   ┌────────────────┐│  │
│  │  │ ████████████░░  │     │ ██████████████░  │   │ ████████████░░ ││  │
│  │  │   92% (通过率)   │     │   98% (通过率)   │   │   95% (通过率) ││  │
│  │  │ ⚠️ 3条告警      │     │ ✅ 正常         │   │ ⚠️ 2条告警     ││  │
│  │  └──────────────────┘     └──────────────────┘   └────────────────┘│  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  质量规则明细                                          [+ 新建规则]  │  │
│  │                                                                     │  │
│  │  ┌──────┬──────────────┬────────┬────────┬─────────┬────────────┐  │  │
│  │  │规则ID │ 规则名称     │ 数据集  │ 类型   │ 级别    │ 状态      │  │  │
│  │  ├──────┼──────────────┼────────┼────────┼─────────┼────────────┤  │  │
│  │  │AR_003│金额必须大于0  │ dm_ar  │准确性  │ 🔴阻断  │ ✅ 已启用  │  │  │
│  │  │AR_004│逾期天数≥0     │ dm_ar  │准确性  │ 🟡警告  │ ✅ 已启用  │  │  │
│  │  │AR_006│AR余额一致性   │ dm_ar  │一致性  │ 🔴阻断  │ ⚠️ 失败   │  │  │
│  │  │CASH_002│收付一致性  │dm_cash │一致性  │ 🔴阻断  │ ✅ 已启用  │  │  │
│  │  └──────┴──────────────┴────────┴────────┴─────────┴────────────┘  │  │
│  │                                                                     │  │
│  │  点击规则行查看详情 & 历史趋势                                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  质量趋势                                              [时间范围 ▼] │  │
│  │                                                                     │  │
│  │   100%│    ╭─╮                    ╭─╮                              │  │
│  │       │   ╭╯ └╮    ╭───╮         ╭╯ └╮                             │  │
│  │    90%│──╯    ╰────╯   ╰─────────╯   ╰──────                       │  │
│  │       │                                                          │  │
│  │    3/15      3/16      3/17        3/18       3/19              │  │
│  │                              日期                                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 12.6 质量告警触发

```java
public class QualityAlertHandler {

    // 规则检查完成后触发
    public void handleCheckResult(RuleCheckResult result) {
        if (result.getStatus() == CheckStatus.PASS) {
            return;
        }

        DataQualityRule rule = getRule(result.getRuleId());

        // 1. 记录日志
        logQualityEvent(result, rule);

        // 2. 发送告警
        if (rule.getSeverity() != Severity.INFO) {
            sendAlert(result, rule);
        }

        // 3. 阻断处理（BLOCKING级别）
        if (rule.getSeverity() == Severity.BLOCKING && result.getStatus() == CheckStatus.FAIL) {
            blockDatasetPublication(rule.getDatasetId(), result);
        }
    }

    // 发送飞书告警
    private void sendAlert(RuleCheckResult result, DataQualityRule rule) {
        AlertCard card = new AlertCard();
        card.setAlertType("data_quality");
        card.setTitle("数据质量告警");
        card.setRuleName(rule.getName());
        card.setDatasetName(getDatasetName(rule.getDatasetId()));
        card.setPassRate(String.format("%.1f%%", result.getPassRate() * 100));
        card.setFailedRecords(result.getInvalidRecords());
        card.setSeverity(rule.getSeverity());

        // 发送到质量负责人
        List<String> receivers = getRuleOwners(rule);
        feishuService.sendAlertCard(receivers, card);
    }
}
```

---

## 十四、Spec Review 修复记录

### 14.1 CRITICAL问题修复

| # | 问题 | 修复方案 | 状态 |
|---|------|----------|------|
| 1 | Doris+ClickHouse冗余 | 明确分工：Doris BI/ad-hoc查询，ClickHouse高频聚合 | ✅ |
| 2 | 数据流图混乱 | 明确Iceberg为唯一真相源，Doris/ClickHouse从Iceberg同步 | ✅ |
| 3 | SAP集成太简化 | 详细方案：SAP JCo + RSA7 Extractors，移除DataServices依赖 | ✅ |
| 4 | CRM双向同步缺失 | 添加冲突解决策略、CRM Webhook同步机制、客户360视图SLA | ✅ |
| 5 | 多租户架构模糊 | 明确RLS行级安全 + Iceberg分区隔离方案 | ✅ |
| 6 | 治理层级不清晰 | 治理层升级为一级架构组件，列级血缘追踪 | ✅ |

### 14.2 HIGH问题修复

| # | 问题 | 修复方案 | 状态 |
|---|------|----------|------|
| 7 | RAG设计不完整 | 补充Embedding模型、混合检索策略、知识版本管理 | ✅ |
| 8 | Flink/dbt边界不清 | 明确分工：Flink实时简单转换，dbt复杂业务逻辑 | ✅ |
| 9 | API标准缺失 | 添加RESTful规范、错误码、分页、限流标准 | ✅ |
| 10 | 本地LLM能力不足 | 升级到Qwen-14B/32B，添加质量门禁与云端降级策略 | ✅ |

---

## 十五、补充设计汇总

### 15.1 需求覆盖检查表

| 原始需求 | 子需求 | 原设计 | 修复后状态 |
|----------|--------|--------|------------|
| 1. 统一接入异构数据 | ERP接入 | ✅ | ✅ |
| | 银行流水 | ✅ | ✅ |
| | 发票/审批 | ✅ | ✅ |
| | CRM接入 | ✅ 详细方案 | ✅ |
| 2. 可视化加工 | 数据集主题 | ✅ | ✅ |
| | 可视化编辑器 | ✅ Dataset Studio | ✅ |
| | 数据质量监控 | ✅ DQC规则引擎 | ✅ |
| 3. 智能看板搭建 | AI自动生成 | ✅ | ✅ |
| 4. 归因决策 | 归因分析 | ✅ | ✅ |
| 5. 实时推送 | 飞书推送 | ✅ | ✅ |
| 6. 自动化输出 | 报告生成 | ✅ | ✅ |

### 15.2 架构改进汇总

| 改进点 | 说明 |
|--------|------|
| OLAP双引擎明确分工 | Doris vs ClickHouse 各司其职 |
| 数据流清晰化 | Iceberg为统一Lake，Doris/ClickHouse同步读取 |
| SAP集成详细方案 | JCo + 标准Extractors，不用DataServices |
| CRM冲突解决 | 权威源原则 + Webhook实时同步 |
| 多租户隔离 | RLS + 分区隔离，配置示例明确 |
| 治理一级组件 | 加密/脱敏/血缘/审计 完整设计 |
| RAG完整架构 | Embedding + 混合检索 + 版本管理 |
| Flink/dbt分工 | 实时简单转换 vs 复杂业务逻辑 |
| API设计标准 | REST规范 + 错误码 + 分页 + 限流 |
| LLM升级 | 14B/32B + 质量门禁 + 云端降级 |

---

*设计修复完成*
*文档版本更新至 v1.2*
