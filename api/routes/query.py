"""数据查询路由"""
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from api.dependencies import DataServiceDep
from api.schemas.query import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/execute", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    data_service: DataServiceDep,
):
    """执行 SQL 查询

    Args:
        request: 查询请求
        data_service: 数据服务

    Returns:
        查询结果
    """
    start_time = time.time()
    try:
        # 安全检查：只允许 SELECT 查询
        sql_stripped = request.sql.strip().upper()
        if not sql_stripped.startswith("SELECT"):
            raise HTTPException(
                status_code=400,
                detail="Only SELECT queries are allowed",
            )

        results = data_service.execute_query(
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables")
async def list_tables(data_service: DataServiceDep):
    """获取可用表列表

    Args:
        data_service: 数据服务

    Returns:
        表列表
    """
    try:
        sql = """
            SELECT
                TABLE_SCHEMA as schema_name,
                TABLE_NAME as table_name,
                TABLE_ROWS as row_count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA IN ('raw', 'std', 'dm')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        results = data_service.execute_query(sql)
        return {"tables": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
