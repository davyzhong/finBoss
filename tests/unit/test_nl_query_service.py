"""NLQueryService 单元测试"""
from unittest.mock import MagicMock


class TestNLQueryServiceValidateSql:
    """_validate_sql() 方法测试"""

    def test_valid_select_query(self):
        """测试合法的 SELECT 查询"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        assert service._validate_sql("SELECT * FROM dm.dm_ar_summary") is True
        assert service._validate_sql("select count(*) from std_ar") is True
        assert service._validate_sql("  SELECT SUM(amount) FROM ar") is True

    def test_reject_dangerous_keywords(self):
        """测试拦截危险 SQL 关键字"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        dangerous_sqls = [
            "SELECT * FROM test; DROP TABLE users",
            "INSERT INTO test VALUES (1)",
            "UPDATE test SET a = 1",
            "DELETE FROM test",
            "DROP TABLE test",
            "TRUNCATE TABLE test",
            "ALTER TABLE test ADD COLUMN a INT",
            "CREATE TABLE test (id INT)",
            "GRANT ALL ON test TO user",
            "REVOKE ALL ON test FROM user",
            "EXEC sp_executesql N'SELECT 1'",
            "EXECUTE proc_name",
            "CALL proc_name()",
        ]
        for sql in dangerous_sqls:
            assert service._validate_sql(sql) is False, f"Should reject: {sql}"

    def test_substring_false_positive(self):
        """测试 sqlglot AST 解析不产生误判（相对于旧版黑名单）"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        # SELECT DELETED — DELETED 不是 DELETE（解析为列名，有效 SELECT）
        assert service._validate_sql("SELECT DELETED FROM test") is True
        # SELECT CALLER — CALLER 不是 CALL（解析为列名，有效 SELECT）
        assert service._validate_sql("SELECT CALLER FROM test") is True
        # SELECT SELECTED — SELECTED 是保留关键字，sqlglot 解析失败（返回 False，比旧版更安全）
        assert service._validate_sql("SELECT SELECTED * FROM test") is False


class TestNLQueryServiceExtractSql:
    """_extract_sql() 方法测试"""

    def test_extract_from_sql_code_block(self):
        """测试从 ```sql ``` 代码块提取"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        text = '根据您的查询，我生成以下 SQL:\n```sql\nSELECT SUM(amount) FROM dm.dm_ar_summary\n```\n这个查询将返回应收总额。'
        result = service._extract_sql(text)
        assert result is not None
        assert "SELECT SUM(amount)" in result
        assert result.strip().endswith("dm.dm_ar_summary")

    def test_extract_from_json(self):
        """测试从 JSON 响应提取"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        text = '{"sql": "SELECT * FROM dm.dm_ar_summary", "explanation": "查询汇总"}'
        result = service._extract_sql(text)
        assert result is not None
        assert "SELECT * FROM dm.dm_ar_summary" in result

    def test_extract_plain_select(self):
        """测试从普通文本提取 SELECT 语句"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        text = "SELECT customer_code, customer_name FROM dm.dm_customer_ar WHERE overdue_amount > 0"
        result = service._extract_sql(text)
        assert result is not None
        assert "SELECT customer_code" in result

    def test_extract_returns_none_on_no_match(self):
        """测试无匹配时返回 None"""
        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=MagicMock(),
            rag_service=MagicMock(),
            clickhouse_service=MagicMock(),
        )
        assert service._extract_sql("这是一段普通文本，没有 SQL") is None
        assert service._extract_sql("") is None


class TestNLQueryServiceQuery:
    """query() 方法测试"""

    def test_query_success_flow(self):
        """测试完整查询流程（成功）"""
        mock_ollama = MagicMock()
        mock_ollama.generate.side_effect = [
            '```sql\nSELECT SUM(total_ar_amount) FROM dm.dm_ar_summary\n```',
            "本月应收总额为 100 万元。",
        ]

        mock_rag = MagicMock()
        mock_rag.search.return_value = [
            {"category": "indicator", "content": "AR 应收总额定义"}
        ]

        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [{"total": 1000000}]

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("本月应收总额是多少")

        assert result["success"] is True
        assert "SELECT" in result["sql"]
        assert result["result"] == [{"total": 1000000}]
        assert result["explanation"] == "本月应收总额为 100 万元。"

    def test_query_rag_fallback_on_error(self):
        """测试 RAG 失败时降级"""
        mock_ollama = MagicMock()
        mock_ollama.generate.side_effect = [
            '```sql\nSELECT * FROM dm.dm_ar_summary\n```',
            "查询结果",
        ]

        mock_rag = MagicMock()
        mock_rag.search.side_effect = Exception("Milvus error")

        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = []

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("test query")

        # RAG 失败不影响查询
        assert result["success"] is True

    def test_query_llm_failure(self):
        """测试 LLM 调用失败"""
        mock_ollama = MagicMock()
        mock_ollama.generate.side_effect = Exception("Ollama connection refused")

        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        mock_ch = MagicMock()

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("test")

        assert result["success"] is False
        assert "LLM 调用失败" in result["error"]

    def test_query_no_sql_extracted(self):
        """测试无法提取 SQL"""
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = "对不起，我无法理解这个查询。"

        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        mock_ch = MagicMock()

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("test")

        assert result["success"] is False
        assert "无法从 LLM 响应中提取 SQL" in result["error"]

    def test_query_dangerous_sql_blocked(self):
        """测试危险 SQL 被拦截"""
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = '```sql\nDROP TABLE dm.dm_ar_summary\n```'

        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        mock_ch = MagicMock()

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("删除所有数据")

        assert result["success"] is False
        assert "危险操作" in result["error"]

    def test_query_sql_execution_failure(self):
        """测试 SQL 执行失败"""
        mock_ollama = MagicMock()
        mock_ollama.generate.side_effect = [
            '```sql\nSELECT * FROM nonexistent_table\n```',
            "解释",
        ]

        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        mock_ch = MagicMock()
        mock_ch.execute_query.side_effect = Exception("Table not found")

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("test")

        assert result["success"] is False
        assert "SQL 执行失败" in result["error"]

    def test_query_result_explain_fallback(self):
        """测试结果解释失败时的降级"""
        mock_ollama = MagicMock()
        mock_ollama.generate.side_effect = [
            '```sql\nSELECT 1\n```',
            Exception("LLM error on explanation"),
        ]

        mock_rag = MagicMock()
        mock_rag.search.return_value = []
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [{"a": 1}, {"a": 2}]

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=mock_ch,
        )
        result = service.query("test")

        # 解释失败不影响查询成功
        assert result["success"] is True
        # 降级为简单的计数说明
        assert "2 条结果" in result["explanation"]


class TestNLQueryServiceHealthCheck:
    """health_check() 方法测试"""

    def test_health_check_all_healthy(self):
        """测试所有服务健康"""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True

        mock_rag = MagicMock()
        mock_rag.is_available.return_value = True

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=MagicMock(),
        )
        result = service.health_check()

        assert result["ollama"] is True
        assert result["milvus"] is True

    def test_health_check_ollama_down(self):
        """测试 Ollama 不可用"""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = False

        mock_rag = MagicMock()
        mock_rag.is_available.return_value = True

        from services.ai.nl_query_service import NLQueryService

        service = NLQueryService(
            ollama_service=mock_ollama,
            rag_service=mock_rag,
            clickhouse_service=MagicMock(),
        )
        result = service.health_check()

        assert result["ollama"] is False
        assert result["milvus"] is True
