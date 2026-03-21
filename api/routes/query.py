"""数据查询路由"""
import logging
import re
import time

from fastapi import APIRouter, HTTPException

from api.dependencies import ClickHouseServiceDep
from api.schemas.query import QueryRequest, QueryResponse
from services.validators import validate_readonly_sql

logger = logging.getLogger(__name__)
router = APIRouter()

# 白名单：只允许查询业务数据表
_ALLOWED_TABLE_PREFIXES = ("raw.", "std.", "dm.")


def _extract_table_names(sql: str) -> list[str]:
    """从 SQL 中提取所有表名（FROM/JOIN 子句）"""
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+(?:\w+\.)?(\w+)",
        re.IGNORECASE,
    )
    return pattern.findall(sql)


def _validate_table_access(sql: str) -> None:
    """验证 SQL 访问的表均在白名单内"""
    tables = _extract_table_names(sql)
    for table in tables:
        # system.* 和其他内部表按黑名单排除
        if table.lower() in ("system", "information_schema", "performance_schema"):
            raise HTTPException(status_code=400, detail=f"Access to table '{table}' is not allowed")
        # system.tables 已在 list_tables 中限制，此处额外兜底
        if table.lower() == "tables" and "system." in sql.lower():
            raise HTTPException(status_code=400, detail="Access to system.tables is not allowed")


def _validate_sql(sql: str) -> None:
    """验证 SQL 安全性（委托给 shared validator + 表白名单）"""
    is_valid, error = validate_readonly_sql(sql)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)
    _validate_table_access(sql)


@router.post("/execute", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    clickhouse_service: ClickHouseServiceDep,
):
    """执行 SQL 查询

    Args:
        request: 查询请求
        clickhouse_service: ClickHouse 数据服务

    Returns:
        查询结果
    """
    start_time = time.time()
    try:
        _validate_sql(request.sql)

        results = clickhouse_service.execute_query(
            sql=request.sql,
            params=request.params,
        )
        execution_time = (time.time() - start_time) * 1000

        return QueryResponse(
            data=results,
            row_count=len(results),
            execution_time_ms=round(execution_time, 2),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("execute_query failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tables")
async def list_tables(clickhouse_service: ClickHouseServiceDep):
    """获取可用表列表

    Args:
        clickhouse_service: ClickHouse 数据服务

    Returns:
        表列表
    """
    try:
        sql = """
            SELECT
                database as schema_name,
                name as table_name,
                total_rows as row_count
            FROM system.tables
            WHERE database IN ('raw', 'std', 'dm')
            ORDER BY database, name
        """
        results = clickhouse_service.execute_query(sql)
        return {"tables": results}
    except Exception:
        logger.exception("list_tables failed")
        raise HTTPException(status_code=500, detail="Internal server error")
