# FinBoss - 企业财务AI信息化系统

> Phase 1 MVP: 核心数据层 + AR应收数据集

## 快速开始

### 前置要求
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+

### 启动基础设施

```bash
# 启动所有组件
docker-compose -f config/docker-compose.yml up -d

# 检查组件状态
docker ps

# 查看日志
docker-compose -f config/docker-compose.yml logs -f
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入金蝶数据库连接信息
```

### 启动 API 服务

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn api.main:app --reload --port 8000
```

### 运行测试

```bash
uv run pytest tests/ -v --cov=services --cov=api
```

## 项目结构

```
finBoss/
├── config/          # 基础设施配置 (Docker, SeaTunnel, Flink, dbt)
├── connectors/      # 数据源连接器 (金蝶, 银行等)
├── schemas/         # Pydantic 数据模型
├── pipelines/       # 数据管道 (接入/处理/数据集市)
├── services/       # 业务服务层
├── api/            # FastAPI REST 接口
├── tests/          # 测试
└── scripts/       # 运维脚本
```

## Phase 1 里程碑

- [ ] Docker Compose 一键启动所有组件
- [ ] SeaTunnel 同步金蝶 AR 数据到 Iceberg
- [ ] Flink 实时处理进入 std 层
- [ ] dbt 生成 dm_ar 数据集
- [ ] FastAPI 提供 AR 查询接口
- [ ] 数据质量规则通过率 > 95%

## 文档

- [系统设计](./docs/superpowers/specs/2026-03-19-finboss-design.md)
- [实施计划](./docs/superpowers/specs/2026-03-19-finboss-implementation-plan.md)
- [Phase 1 结构设计](./docs/superpowers/specs/2026-03-19-finboss-phase1-structure.md)
