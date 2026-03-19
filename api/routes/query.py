"""数据查询路由"""
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from api.dependencies import DataServiceDep
from api.schemas.query import QueryRequest, QueryResponse

router = APIRouter()

# 危险 SQL 模式黑名单
_DANGEROUS_PATTERNS = [
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bINSERT\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r"\bCREATE\b", re.IGNORECASE),
    re.compile(r"\bGRANT\b", re.IGNORECASE),
    re.compile(r"\bREVOKE\b", re.IGNORECASE),
    re.compile(r";\s*\w+", re.IGNORECASE),  # 多语句: ;后面的内容
]

# 仅允许的表名模式
_ALLOWED_TABLES = re.compile(r"^\w+$")


def _validate_sql(sql: str) -> None:
    """验证 SQL 安全性

    Raises:
        HTTPException: 如果 SQL 包含危险模式或不是 SELECT
    """
    sql_upper = sql.strip().upper()

    # 必须以 SELECT 开头
    if not sql_upper.startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed",
        )

    # 检查危险模式
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(sql):
            raise HTTPException(
                status_code=400,
                detail=f"Forbidden SQL pattern detected: {pattern.pattern}",
            )


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
        _validate_sql(request.sql)

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
