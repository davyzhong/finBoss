"""SQL 安全验证工具"""
import re

# 危险 SQL 模式黑名单
# (?!\w) 确保关键字不以字母/数字结尾，防止匹配到 DELETED、EXECUTE 等合法词
_DANGEROUS_KEYWORD = r"\b{kw}\b(?!\w)"

DANGEROUS_PATTERNS = [
    re.compile(_DANGEROUS_KEYWORD.format(kw=kw), re.IGNORECASE)
    for kw in (
        "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE",
        "ALTER", "CREATE", "GRANT", "REVOKE",
        "EXEC", "EXECUTE", "CALL", "KILL", "SHUTDOWN",
    )
] + [
    # 阻止多语句注入：分号后跟非空白字符
    re.compile(r";\s*[^\s]"),
    # 阻止 INTO OUTFILE 等文件写入
    re.compile(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", re.IGNORECASE),
]


def validate_readonly_sql(sql: str) -> tuple[bool, str]:
    """验证 SQL 为只读 SELECT 查询

    Args:
        sql: SQL 语句

    Returns:
        (is_valid, error_message) — is_valid=True 时 error_message 为空
    """
    sql_stripped = sql.strip().upper()

    # 必须以 SELECT 开头
    if not sql_stripped.startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # 检查危险模式
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(sql):
            return False, f"Forbidden SQL pattern detected: {pattern.pattern}"

    return True, ""
