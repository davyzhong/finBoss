"""数据查询路由"""
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from api.dependencies import ClickHouseServiceDep
from api.schemas.query import QueryRequest, QueryResponse
from services.validators import validate_readonly_sql

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_sql(sql: str) -> None:
    """验证 SQL 安全性（委托给 shared validator）"""
    is_valid, error = validate_readonly_sql(sql)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)


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
    except Exception as e:
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
    except Exception as e:
        logger.exception("list_tables failed")
        raise HTTPException(status_code=500, detail="Internal server error")
