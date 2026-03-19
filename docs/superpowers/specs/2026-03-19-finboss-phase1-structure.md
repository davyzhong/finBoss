# FinBoss Phase 1 项目结构设计

> 版本：v1.0
> 日期：2026-03-19
> 状态：已批准

---

## 一、技术栈总览

| 类别 | 技术选型 | 说明 |
|------|----------|------|
| 容器编排 | Docker Compose | 本地开发环境快速验证 |
| 数据集成 | SeaTunnel 2.3.3 | CDC 增量同步 + 批量接入 |
| 数据湖 | Apache Iceberg 1.5 | 统一存储层（raw + std） |
| 对象存储 | MiniIO | S3 兼容，本地替代 AWS S3 |
| OLAP 引擎 | Doris 2.1 + ClickHouse | 数据集市查询层 |
| 实时处理 | Flink 1.18 | 标准化处理层 |
| 批处理 | dbt | 数据集模型管理 |
| 后端服务 | Python 3.11 + FastAPI + SQLAlchemy | API 服务层 |
| 数据库 | 金蝶星空 V7 (MSSQL) | 数据源 |

---

## 二、项目目录结构

```
finBoss/
├── docs/                        # 文档
│   ├── superpowers/             # 设计文档
│   │   ├── specs/              # 规格文档
│   │   └── plans/              # 实施计划
│   └── ARCHITECTURE.md         # 架构说明
├── config/                      # 配置中心
│   ├── docker-compose.yml      # 基础设施组件编排
│   ├── seatunnel/              # SeaTunnel 配置
│   │   ├── jobs/               # 作业定义
│   │   │   ├── kingdee_ar_cdc.yml
│   │   │   └── kingdee_ar_batch.yml
│   │   └── connectors/         # 连接器配置
│   ├── flink/                  # Flink SQL 作业
│   │   ├── sql/
│   │   │   ├── std_ar.sql     # AR 标准化处理
│   │   │   └── quality.sql    # 质控检查
│   │   └── job.yaml           # Flink 作业配置
│   ├── dbt/                    # dbt 项目
│   │   └── finboss/
│   │       ├── dbt_project.yml
│   │       ├── models/
│   │       │   ├── raw/       # 原始层模型
│   │       │   ├── std/       # 标准层模型
│   │       │   └── dm/        # 数据集市层模型
│   │       ├── macros/        # 宏定义
│   │       └── tests/         # dbt 测试
│   └── feishu/                 # 飞书配置（Phase 3）
├── connectors/                  # 数据源连接器
│   ├── kingdee/                # 金蝶连接器
│   │   ├── __init__.py
│   │   ├── client.py          # 金蝶 API 客户端
│   │   ├── jdbc.py            # 金蝶数据库连接
│   │   └── models.py          # 数据模型
│   ├── bank/                   # 银行流水连接器（Phase 4）
│   │   └── __init__.py
│   └── common/                 # 公共连接器基类
│       ├── __init__.py
│       └── base.py
├── schemas/                     # 数据模型定义（Pydantic）
│   ├── __init__.py
│   ├── raw/                    # 原始层 Schema
│   │   ├── __init__.py
│   │   └── kingdee.py         # 金蝶原始表映射
│   ├── std/                    # 标准层 Schema
│   │   ├── __init__.py
│   │   ├── ar.py              # AR 应收标准模型
│   │   └── common.py          # 公共字段模型
│   └── dm/                     # 数据集市 Schema
│       ├── __init__.py
│       └── ar.py               # AR 数据集市模型
├── pipelines/                   # 数据管道
│   ├── __init__.py
│   ├── ingestion/              # 接入层
│   │   ├── __init__.py
│   │   └── kingdee_ar.py     # 金蝶 AR 数据接入
│   ├── processing/            # 处理层
│   │   ├── __init__.py
│   │   ├── std_ar.py          # AR 标准化处理
│   │   └── quality.py         # 数据质量检查
│   └── marts/                 # 数据集市层
│       ├── __init__.py
│       └── dm_ar.py           # AR 数据集生成
├── services/                    # 业务服务层
│   ├── __init__.py
│   ├── ar_service.py          # AR 业务服务
│   ├── data_service.py        # 数据查询服务
│   └── quality_service.py      # 质控服务
├── api/                         # API 层（FastAPI）
│   ├── __init__.py
│   ├── main.py                # 应用入口
│   ├── config.py              # 配置加载
│   ├── routes/                # 路由
│   │   ├── __init__.py
│   │   ├── ar.py             # AR 相关路由
│   │   └── query.py          # 数据查询路由
│   ├── schemas/               # API 请求/响应模型
│   │   ├── __init__.py
│   │   ├── ar.py
│   │   └── query.py
│   └── dependencies.py        # 依赖注入
├── tests/                       # 测试
│   ├── __init__.py
│   ├── conftest.py            # pytest 配置
│   ├── unit/                  # 单元测试
│   │   ├── __init__.py
│   │   ├── test_ar_service.py
│   │   └── test_schemas.py
│   ├── integration/           # 集成测试
│   │   ├── __init__.py
│   │   └── test_pipeline.py
│   └── data/                  # 数据质量测试
│       ├── __init__.py
│       └── test_ar_quality.py
├── scripts/                     # 运维脚本
│   ├── setup.sh                # 环境初始化
│   ├── init_dbt.sh            # dbt 初始化
│   ├── quality_check.py        # 质控检查脚本
│   └── seed_test_data.py       # 测试数据填充
├── pyproject.toml               # Python 项目配置
├── uv.lock                      # 依赖锁定文件
├── .env.example                # 环境变量模板
├── .gitignore
└── README.md
```

---

## 三、数据流向

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Phase 1 数据流向                              │
└─────────────────────────────────────────────────────────────────────┘

金蝶 MSSQL (V7)
     │
     │  SeaTunnel CDC (增量) + 批量 (存量)
     ▼
Iceberg: raw_kingdee.ar_verify          [原始层]
     │
     │  Flink SQL (实时流处理)
     ▼
Iceberg: std_ar                          [标准层]
     │
     │  dbt (批处理聚合)
     ▼
Doris: dm_ar                             [数据集市层]
     │
     │  FastAPI (REST API)
     ▼
客户端 / 可视化看板
```

### 数据表映射

| 源系统 | 源表 | raw 层 | std 层 | dm 层 |
|--------|------|--------|--------|-------|
| 金蝶 | t_ar_verify | raw_kingdee.ar_verify | std_ar | dm_ar |
| 金蝶 | t_bd_customer | raw_kingdee.customer | std_customer | - |

---

## 四、Docker Compose 组件清单

| 组件 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| zookeeper | confluentinc/cp-zookeeper:7.5.0 | 2181 | Kafka/ZK 协调 |
| kafka | confluentinc/cp-kafka:7.5.0 | 9092 | 消息队列 |
| minio | minio/minio:latest | 9000/9001 | 对象存储 |
| seatunnel | apache/seatunnel:2.3.3 | 5801 | 数据集成 |
| doris-fe | apache/doris:2.1.5 | 8030/9030 | OLAP 前端 |
| doris-be | apache/doris:2.1.5 | 8040 | OLAP 后端 |
| clickhouse | clickhouse/clickhouse:23.8 | 8123/9000 | 高频查询 |
| flink-jobmanager | flink:1.18.1 | 8081 | 实时处理 |
| flink-taskmanager | flink:1.18.1 | - | 实时处理 |
| fastapi | 自构建 | 8000 | API 服务 |

---

## 五、模块职责说明

### 5.1 connectors/

金蝶数据源连接器封装，包括：
- `client.py`: 金蝶 API REST 客户端封装
- `jdbc.py`: MSSQL JDBC 连接管理
- `models.py`: 金蝶数据模型定义

### 5.2 schemas/

使用 Pydantic 定义数据模型：
- raw 层：与金蝶原始表一一映射
- std 层：标准化后的业务模型
- dm 层：数据集市聚合模型

### 5.3 pipelines/

数据加工流水线：
- `ingestion/`: 从金蝶接入原始数据
- `processing/`: 标准化处理 + 质量检查
- `marts/`: 数据集生成

### 5.4 services/

业务服务层，封装数据操作：
- `ar_service.py`: AR 业务逻辑
- `data_service.py`: 跨数据源查询
- `quality_service.py`: 数据质量规则

### 5.5 api/

FastAPI REST 接口：
- `/api/v1/ar/*`: AR 相关接口
- `/api/v1/query/*`: 数据查询接口

---

## 六、环境变量配置

```bash
# .env.example

# 金蝶数据库
KINGDEE_DB_HOST=localhost
KINGDEE_DB_PORT=1433
KINGDEE_DB_NAME=kingdee
KINGDEE_DB_USER=
KINGDEE_DB_PASSWORD=

# MiniIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=finboss

# Doris
DORIS_FE_HOST=localhost
DORIS_FE_PORT=9030
DORIS_USER=root
DORIS_PASSWORD=

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# Iceberg
ICEBERG_WAREHOUSE=s3://finboss/warehouse

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

---

## 七、验收标准

Phase 1 结束时应满足以下条件：

```
□ Docker Compose 一键启动所有组件成功
□ SeaTunnel 成功同步金蝶 AR 数据到 Iceberg raw 层
□ Flink 实时处理后数据进入 Iceberg std 层，延迟 < 10 分钟
□ dbt 模型生成 dm_ar 数据集，在 Doris 可查询
□ 数据质量规则通过率 > 95%
□ FastAPI 提供 AR 数据查询接口（/api/v1/ar/summary, /api/v1/ar/detail）
□ 单元测试覆盖核心服务代码，覆盖率 > 70%
```

---

## 八、关联文档

| 文档 | 路径 |
|------|------|
| 系统设计文档 | docs/superpowers/specs/2026-03-19-finboss-design.md |
| 实施计划 | docs/superpowers/specs/2026-03-19-finboss-implementation-plan.md |

---

*Phase 1 项目结构设计版本：v1.0*
