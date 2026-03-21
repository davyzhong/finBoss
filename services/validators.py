"""SQL 安全验证工具

使用 sqlglot 解析 SQL AST，强制白名单验证：
- 只允许 SELECT 语句
- 递归检查所有子查询、CTE 中是否含危险操作
- 黑名单保留作为最后防线
"""
from __future__ import annotations

import re
from typing import Any

import sqlglot

# sqlglot 的语句类型常量（用于检测非 SELECT 语句）
import sqlglot.expressions as exp

# 危险关键词黑名单（保留作为额外防线）
_DANGEROUS_KEYWORD = r"\b{kw}\b(?!\w)"

DANGEROUS_PATTERNS = [
    re.compile(_DANGEROUS_KEYWORD.format(kw=kw), re.IGNORECASE)
    for kw in (
        "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE",
        "ALTER", "CREATE", "GRANT", "REVOKE",
        "EXEC", "EXECUTE", "CALL", "KILL", "SHUTDOWN",
    )
] + [
    # 阻止多语句注入
    re.compile(r";\s*[^\s]"),
    # 阻止文件写入
    re.compile(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", re.IGNORECASE),
]

# 禁止的顶层语句类型（sqlglot 表达式类名）
_FORBIDDEN_STATEMENT_TYPES = frozenset([
    "Drop", "Delete", "Insert", "Update", "Truncate",
    "Alter", "Create", "Grant", "Revoke", "Execute",
    "Call", "Kill", "Shutdown",
])


def _walk_forbidden_ops(node: sqlglot.Expression) -> list[str]:
    """递归遍历 AST，收集所有危险操作类型名。"""
    ops: list[str] = []
    name = node.__class__.__name__
    if name in _FORBIDDEN_STATEMENT_TYPES:
        ops.append(name)
    for child in node.iter_expressions():
        ops.extend(_walk_forbidden_ops(child))
    return ops


def validate_readonly_sql(sql: str) -> tuple[bool, str]:
    """验证 SQL 为只读 SELECT 查询（白名单优先，黑名单兜底）

    Args:
        sql: SQL 语句

    Returns:
        (is_valid, error_message) — is_valid=True 时 error_message 为空
    """
    # Step 1: 黑名单兜底（快速拒绝明显攻击）
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(sql):
            return False, f"Forbidden SQL pattern detected: {pattern.pattern}"

    # Step 2: sqlglot 白名单解析
    try:
        statements = sqlglot.parse(sql, read=None, dialect="clickhouse")
    except sqlglot.errors.SqlglotError as e:
        return False, f"SQL parse error: {e}"

    if not statements:
        return False, "Empty SQL statement"

    # Step 3: 验证每条语句都是安全的 SELECT
    for stmt in statements:
        stmt_name = stmt.__class__.__name__

        # 顶层语句必须是 SELECT 系列
        if stmt_name not in ("Select", "Union", "Intersect", "Except"):
            return False, f"Only SELECT statements are allowed; found: {stmt_name}"

        # 递归检查所有子查询/CTE 中是否有危险操作
        forbidden = _walk_forbidden_ops(stmt)
        if forbidden:
            return False, f"Forbidden operation in query: {', '.join(forbidden)}"

    return True, ""
