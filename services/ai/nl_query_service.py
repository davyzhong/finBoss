"""自然语言查询服务 - NL → SQL → Result → NL"""

from typing import Any

from services.ai.ollama_service import OllamaService
from services.ai.prompts import NL_QUERY_SYSTEM_PROMPT, RESULT_EXPLAIN_PROMPT
from services.ai.rag_service import RAGService
from services.clickhouse_service import ClickHouseDataService
from services.validators import validate_readonly_sql


class NLQueryService:
    """自然语言查询服务"""

    def __init__(
        self,
        ollama_service: OllamaService | None = None,
        rag_service: RAGService | None = None,
        clickhouse_service: ClickHouseDataService | None = None,
    ):
        self.ollama = ollama_service or OllamaService()
        self.rag = rag_service or RAGService()
        self.clickhouse = clickhouse_service or ClickHouseDataService()

    def _validate_sql(self, sql: str) -> bool:
        """验证 SQL 安全性（仅允许 SELECT）"""
        is_valid, _ = validate_readonly_sql(sql)
        return is_valid

    def query(self, natural_language: str) -> dict[str, Any]:
        """执行自然语言查询

        Args:
            natural_language: 用户的自然语言查询

        Returns:
            {sql, explanation, result, success, error}
        """
        # Step 1: 先检索 RAG 知识库，获取相关背景知识
        rag_context = ""
        try:
            docs = self.rag.search(natural_language, top_k=3)
            if docs:
                rag_context = "\n\n## 上下文知识:\n" + "\n".join(
                    f"- [{d['category']}] {d['content']}" for d in docs
                )
        except Exception:
            rag_context = ""

        # Step 2: 调用 LLM 生成 SQL
        try:
            response = self.ollama.generate(
                prompt=natural_language + rag_context,
                system=NL_QUERY_SYSTEM_PROMPT,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"LLM 调用失败: {e}",
                "sql": None,
                "result": None,
                "explanation": None,
            }

        # Step 3: 解析 LLM 响应，提取 SQL
        sql = self._extract_sql(response)
        if not sql:
            return {
                "success": False,
                "error": "无法从 LLM 响应中提取 SQL",
                "sql": response,
                "result": None,
                "explanation": None,
            }

        # Step 4: 验证 SQL
        if not self._validate_sql(sql):
            return {
                "success": False,
                "error": "SQL 包含危险操作，已被拦截",
                "sql": sql,
                "result": None,
                "explanation": None,
            }

        # Step 5: 执行 SQL
        try:
            result = self.clickhouse.execute_query(sql)
        except Exception as e:
            return {
                "success": False,
                "error": f"SQL 执行失败: {e}",
                "sql": sql,
                "result": None,
                "explanation": None,
            }

        # Step 6: 生成自然语言解释
        try:
            explanation = self.ollama.generate(
                prompt=RESULT_EXPLAIN_PROMPT.format(
                    query=natural_language,
                    sql=sql,
                    result=str(result[:10]),  # 限制结果长度
                ),
                system="你是一个专业的财务数据分析助手，用简洁的中文解释查询结果。",
            )
        except Exception:
            explanation = f"查询返回 {len(result)} 条结果"

        return {
            "success": True,
            "sql": sql,
            "result": result,
            "explanation": explanation,
            "error": None,
        }

    def _extract_sql(self, text: str) -> str | None:
        """从 LLM 响应中提取 SQL"""
        import re

        # 尝试从 ```sql ... ``` 块中提取
        match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试从 JSON 中提取
        match = re.search(r'"sql"\s*:\s*"([^"]+)"', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试直接找 SELECT 语句
        match = re.search(r"(SELECT\s+.*?)(?:\n|$)", text, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
            if sql.upper().startswith("SELECT"):
                return sql

        return None

    def health_check(self) -> dict[str, Any]:
        """检查所有依赖服务状态"""
        return {
            "ollama": self.ollama.is_available(),
            "milvus": self.rag.is_available(),
        }
