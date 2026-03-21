"""SQL 安全验证工具单元测试"""
import pytest

from services.validators import (
    DANGEROUS_PATTERNS,
    validate_readonly_sql,
)


class TestValidateReadonlySqlBlacklist:
    """黑名单兜底测试"""

    def test_rejects_drop(self):
        is_valid, _ = validate_readonly_sql("DROP TABLE users")
        assert is_valid is False

    def test_rejects_delete(self):
        is_valid, _ = validate_readonly_sql("DELETE FROM users WHERE id = 1")
        assert is_valid is False

    def test_rejects_insert(self):
        is_valid, _ = validate_readonly_sql("INSERT INTO users VALUES (1, 'test')")
        assert is_valid is False

    def test_rejects_update(self):
        is_valid, _ = validate_readonly_sql("UPDATE users SET name = 'hack' WHERE id = 1")
        assert is_valid is False

    def test_rejects_truncate(self):
        is_valid, _ = validate_readonly_sql("TRUNCATE TABLE users")
        assert is_valid is False

    def test_rejects_alter(self):
        is_valid, _ = validate_readonly_sql("ALTER TABLE users ADD COLUMN hack TEXT")
        assert is_valid is False

    def test_rejects_create(self):
        is_valid, _ = validate_readonly_sql("CREATE TABLE hack (id INT)")
        assert is_valid is False

    def test_rejects_grant(self):
        is_valid, _ = validate_readonly_sql("GRANT ALL ON users TO hacker")
        assert is_valid is False

    def test_rejects_revoke(self):
        is_valid, _ = validate_readonly_sql("REVOKE ALL ON users FROM hacker")
        assert is_valid is False

    def test_rejects_exec(self):
        is_valid, _ = validate_readonly_sql("EXEC sp_executesql N'SELECT 1'")
        assert is_valid is False

    def test_rejects_execute(self):
        is_valid, _ = validate_readonly_sql("EXECUTE proc_name")
        assert is_valid is False

    def test_rejects_call(self):
        is_valid, _ = validate_readonly_sql("CALL proc_name()")
        assert is_valid is False

    def test_rejects_kill(self):
        is_valid, _ = validate_readonly_sql("KILL 123")
        assert is_valid is False

    def test_rejects_shutdown(self):
        is_valid, _ = validate_readonly_sql("SHUTDOWN")
        assert is_valid is False

    def test_rejects_multistatement_injection(self):
        """分号后跟非空白字符视为注入"""
        is_valid, _ = validate_readonly_sql("SELECT 1; DROP TABLE users")
        assert is_valid is False

    def test_rejects_into_outfile(self):
        is_valid, _ = validate_readonly_sql("SELECT * FROM users INTO OUTFILE '/tmp/hack'")
        assert is_valid is False

    def test_rejects_into_dumpfile(self):
        is_valid, _ = validate_readonly_sql("SELECT * INTO DUMPFILE '/tmp/hack'")
        assert is_valid is False


class TestValidateReadonlySqlGlotWhitelist:
    """sqlglot AST 白名单测试"""

    def test_accepts_simple_select(self):
        is_valid, _ = validate_readonly_sql("SELECT * FROM dm.dm_ar_summary")
        assert is_valid is True

    def test_accepts_select_with_where(self):
        is_valid, _ = validate_readonly_sql(
            "SELECT company_code, SUM(total_ar_amount) FROM dm.dm_ar_summary WHERE stat_date = '2026-03-01' GROUP BY company_code"
        )
        assert is_valid is True

    def test_accepts_select_with_join(self):
        is_valid, _ = validate_readonly_sql(
            "SELECT a.company_code, b.customer_name FROM dm.dm_ar_summary a JOIN dm.dm_customer_ar b ON a.company_code = b.company_code"
        )
        assert is_valid is True

    def test_accepts_select_with_subquery(self):
        is_valid, _ = validate_readonly_sql(
            "SELECT * FROM (SELECT company_code, total_ar_amount FROM dm.dm_ar_summary) AS sub"
        )
        assert is_valid is True

    def test_rejects_non_select_statement(self):
        """非 SELECT 语句（DELETE/INSERT/UPDATE 等）被 sqlglot AST 验证拦截"""
        is_valid, _ = validate_readonly_sql("SHOW TABLES")
        assert is_valid is False

    def test_rejects_set_statement(self):
        is_valid, _ = validate_readonly_sql("SET max_execution_time = 1000")
        assert is_valid is False

    def test_rejects_use_statement(self):
        is_valid, _ = validate_readonly_sql("USE some_database")
        assert is_valid is False

    def test_rejects_with_clause_mutation(self):
        """WITH 子句中的危险操作"""
        is_valid, _ = validate_readonly_sql(
            "WITH malicious AS (DELETE FROM users) SELECT * FROM dm.dm_ar_summary"
        )
        assert is_valid is False

    def test_rejects_union_with_mutation(self):
        """UNION 中的危险操作"""
        is_valid, _ = validate_readonly_sql(
            "SELECT 1 UNION SELECT * FROM (DELETE FROM users) AS t"
        )
        assert is_valid is False

    def test_empty_sql_rejected(self):
        is_valid, _ = validate_readonly_sql("")
        assert is_valid is False

    def test_whitespace_only_sql_rejected(self):
        is_valid, _ = validate_readonly_sql("   ")
        assert is_valid is False

    def test_parse_error_rejected(self):
        """语法错误被 sqlglot 解析阶段捕获"""
        is_valid, msg = validate_readonly_sql("SELECT * FROM WHERE id = 1")
        assert is_valid is False
        assert "parse error" in msg.lower()

    def test_select_deleted_column_valid(self):
        """SELECT DELETED — DELETED 是列名，合法"""
        is_valid, _ = validate_readonly_sql("SELECT DELETED FROM some_table")
        assert is_valid is True

    def test_select_caller_column_valid(self):
        """SELECT CALLER — CALLER 是列名，合法"""
        is_valid, _ = validate_readonly_sql("SELECT CALLER FROM some_table")
        assert is_valid is True

    def test_union_select_allowed(self):
        """UNION 查询是合法的只读操作"""
        is_valid, _ = validate_readonly_sql(
            "SELECT company_code FROM dm.dm_ar_summary UNION ALL SELECT company_code FROM dm.dm_customer_ar"
        )
        assert is_valid is True
