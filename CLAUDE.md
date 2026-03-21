# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FinBoss is an enterprise financial AI data platform connecting heterogeneous ERP systems, aggregating data, and providing AI-driven analytics and reporting. Currently in **Phase 3** (企业集成与增强) - Feishu bot + attribution analysis + knowledge versioning.

**Tech Stack**: Python 3.11, FastAPI, ClickHouse, Ollama, Milvus, Apache Iceberg, SeaTunnel, Flink, Kafka, MinIO, dbt

## Development Commands

### Setup & Installation
```bash
# Install dependencies
uv sync

# Copy environment variables template
cp .env.example .env
# Edit .env with actual credentials (especially KINGDEE_DB_* for Kingdee ERP connection)
```

### Running the Application
```bash
# Start infrastructure services (Phase 1: ClickHouse, Kafka, MinIO, Flink)
# Phase 2 also includes: Milvus (vector DB), Ollama (LLM), etcd
docker-compose -f config/docker-compose.yml up -d

# Pull Ollama models (first time only, ~4GB each)
docker exec finboss-ollama ollama pull qwen2.5:7b
docker exec finboss-ollama ollama pull nomic-embed-text

# Initialize financial knowledge base
uv run python scripts/ingest_financial_knowledge.py

# Start FastAPI development server
uv run uvicorn api.main:app --reload --port 8000

# API documentation available at:
# - Swagger UI: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

### Testing
```bash
# Run all tests with coverage
uv run pytest tests/ -v --cov=services --cov=api

# Run specific test file
uv run pytest tests/unit/test_ar_service.py -v

# Run single test
uv run pytest tests/unit/test_ar_service.py::test_function_name -v

# Run with coverage report
uv run pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
```

### Code Quality
```bash
# Linting
uv run ruff check .

# Auto-format
uv run ruff format .

# Type checking
uv run mypy .
```

### Data Management
```bash
# Seed test data into ClickHouse
uv run python scripts/simple_seed_data.py

# Run data quality checks
uv run python scripts/quality_check.py
```

## Architecture

### Three-Layer Data Model

**Data flows**: Source Systems → SeaTunnel (CDC) → Iceberg (raw) → Flink/dbt → Iceberg (std) → ClickHouse (dm)

1. **raw/** - Raw ingested data from source systems (Kingdee, banks, invoices, etc.)
2. **std/** - Standardized and cleaned data with consistent schemas
3. **dm/** - Data mart layer with aggregated business metrics and KPIs

Each layer has corresponding Pydantic models in `schemas/` directory:
- `schemas/raw/kingdee.py` - Raw ERP data models
- `schemas/std/ar.py` - Standardized AR records
- `schemas/dm/ar.py` - Aggregated AR summaries and customer metrics

### Service Layer Pattern

- **`services/clickhouse_service.py`** - Primary data access service for ClickHouse queries
- **`services/quality_service.py`** - Data quality validation and monitoring
- **`services/ar_service.py`** - AR-specific business logic
- **`services/ai/ollama_service.py`** - Ollama LLM wrapper (local inference)
- **`services/ai/rag_service.py`** - RAG pipeline (Milvus vector search)
- **`services/ai/nl_query_service.py`** - Natural language → SQL → result → NL explanation

Services use dependency injection via FastAPI's `Depends()`:
```python
# api/dependencies.py defines injectable services
ClickHouseServiceDep = Annotated[ClickHouseDataService, Depends(get_clickhouse_service)]

# Routes use them as parameters
@router.get("/summary")
async def get_ar_summary(service: ClickHouseServiceDep):
    return service.get_ar_summary()
```

### Configuration Management

Nested Pydantic Settings classes with **critical** requirement:

```python
class KingdeeDBConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="kingdee_",  # Maps KINGDEE_* env vars
        env_file=".env",
        extra="ignore",  # REQUIRED for nested configs
    )
```

**Important**: All nested config classes must have `extra="ignore"` to avoid validation errors.

Environment variable naming convention:
- `KINGDEE_DB_HOST` → `kingdee.host`
- `CLICKHOUSE_HOST` → `clickhouse.host`
- `MINIO_ACCESS_KEY` → `minio.access_key`

### API Route Structure

- **`api/routes/ar.py`** - AR endpoints: `/api/v1/ar/*`
  - `/summary` - Company-level AR aggregations
  - `/customer` - Customer-level AR metrics
  - `/detail` - Individual AR records
  - `/quality-check` - Data quality validation
- **`api/routes/query.py`** - SQL execution endpoints: `/api/v1/query/*`
  - `/execute` - Execute read-only SQL queries
  - `/tables` - List available tables
- **`api/routes/ai.py`** - AI endpoints: `/api/v1/ai/*` (Phase 2)
  - `/query` - Natural language query (NL → SQL → result → NL)
  - `/health` - Check Ollama + Milvus status
  - `/rag/search` - Search knowledge base
  - `/rag/ingest` - Add document to knowledge base
  - `/rag/ingest/batch` - Batch add documents

## ClickHouse Integration

### Data Access Pattern

ClickHouse driver returns tuples, not dictionaries. The `ClickHouseDataService` handles conversion:

```python
result = self.client.execute(sql, params, with_column_types=True)
data, column_types = result  # Unpack tuple
column_names = [col[0] for col in column_types]
return [dict(zip(column_names, row)) for row in data]
```

### SQL Security

User-submitted SQL queries are validated in two stages (in `services/validators.py:validate_readonly_sql`):
1. Blacklist quick-reject for obviously dangerous patterns (DROP, DELETE, INSERT, etc.)
2. sqlglot AST parsing: verifies the top-level statement is SELECT/UNION and recursively checks all subqueries/CTEs for forbidden operations.

Only SELECT-family queries are allowed.

## Testing Conventions

### Test Organization
- `tests/unit/` - Unit tests for services and utilities
- `tests/integration/` - Integration tests for API endpoints and database
- `tests/conftest.py` - Shared pytest fixtures

### Key Test Files
- `tests/unit/test_validators.py` - SQL security validation (sqlglot AST whitelist)
- `tests/unit/test_clickhouse_service.py` - ClickHouse query service + limit/table-name validation
- `tests/unit/test_feishu_client.py` - Feishu client signature verification and token caching
- `tests/unit/test_ollama_service.py` - Ollama LLM service (uses `http_client` dependency injection for mockability)

### Service Cache Isolation
All `@lru_cache` service factories are cleared between tests via `conftest.py`'s `autouse` fixture. Never share service instances across tests.

### Test Data

Use factory fixtures from `conftest.py`:
- `sample_ar_records` - List of StdARRecord objects
- `sample_dm_summary` - DMARSummary object

For database tests, use ClickHouse test containers or mock the `ClickHouseDataService`.

## Common Tasks

### Adding a New Data Source

1. Create connector in `connectors/<source_name>/`
2. Add raw schema model in `schemas/raw/<source>.py`
3. Create SeaTunnel job configuration in `config/seatunnel/jobs/`
4. Add standardized model in `schemas/std/`
5. Create Flink processing job or dbt model
6. Add data mart model in `schemas/dm/`
7. Create service method in appropriate service class
8. Add API endpoint in `api/routes/`
9. Write tests for each layer

### Adding a New API Endpoint

1. Define Pydantic response model in `api/schemas/`
2. Add service method if needed
3. Create route handler in appropriate `api/routes/*.py` file
4. Register router in `api/main.py` if new route file
5. Add request/response examples to endpoint docstring
6. Write integration test in `tests/integration/`

### Running Data Pipelines

Currently Phase 1 uses static test data. For production:
1. SeaTunnel jobs will sync from Kingdee ERP → Iceberg raw layer
2. Flink jobs process raw → std layer (real-time)
3. dbt models generate std → dm layer (batch)

## Important Files

- **`api/config.py`** - All configuration classes. Remember `extra="ignore"` for nested configs
- **`services/clickhouse_service.py`** - Primary database access layer
- **`api/dependencies.py`** - Dependency injection configuration
- **`scripts/simple_seed_data.py`** - Test data generation for development
- **`docs/TEST_REPORT.md`** - Phase 1 API testing results and known issues

## Known Issues & Gotchas

### Port Conflicts

ClickHouse native port is mapped to **9002** (not 9000) to avoid conflict with MinIO's default port 9000.

### Pydantic Settings Validation

If you see `ValidationError: Field required` for config classes, ensure nested configs have `extra="ignore"` in `model_config`.

### ClickHouse vs Doris

Current implementation uses **ClickHouse** as primary OLAP engine, not Doris. Doris configuration exists in docker-compose but is commented out. All data services query ClickHouse.
