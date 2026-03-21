"""自然语言查询服务 - NL → SQL → Result → NL"""

from typing import Any

from services.ai.ollama_service import OllamaService
from services.ai.rag_service import RAGService
from services.clickhouse_service import ClickHouseDataService

# ClickHouse 支持的表及字段信息（用于 Schema 描述）
DATABASE_SCHEMA = """
## FinBoss 数据库架构

### dm.dm_ar_summary (AR 汇总表)
| 字段 | 类型 | 描述 |
|------|------|------|
| stat_date | Date | 统计日期 |
| company_code | String | 公司代码 |
| company_name | String | 公司名称 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| received_amount | Decimal(18,2) | 已收金额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 总单数 |
| overdue_rate | Float32 | 逾期率 |

### dm.dm_customer_ar (客户 AR 表)
| 字段 | 类型 | 描述 |
|------|------|------|
| customer_code | String | 客户代码 |
| customer_name | String | 客户名称 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |

### std.std_ar (AR 明细表)
| 字段 | 类型 | 描述 |
|------|------|------|
| id | String | 单据ID |
| bill_no | String | 单据编号 |
| bill_date | DateTime | 单据日期 |
| bill_amount | Decimal(18,2) | 单据金额 |
| customer_name | String | 客户名称 |
| is_overdue | Bool | 是否逾期 |
| days_overdue | Int32 | 逾期天数 |
| company_code | String | 公司代码 |
"""

SYSTEM_PROMPT = f"""你是一个专业的财务数据分析助手，帮助用户用自然语言查询财务数据。

## 工作流程
1. 理解用户的自然语言查询
2. 根据数据库架构生成 ClickHouse SQL
3. 返回结构化的查询结果
4. 用自然语言解释结果

## 数据库架构
{DATABASE_SCHEMA}

## 重要规则
- 只生成 SELECT 查询，禁止 INSERT/UPDATE/DELETE/DROP
- 金额字段使用 Decimal(18,2)
- 日期使用 'YYYY-MM-DD' 格式
- 公司代码如 C001, C002, C003
- SQL 中表名使用完全限定名: dm.dm_ar_summary, dm.dm_customer_ar, std.std_ar
- 如果查询涉及金额总计，使用 SUM() 聚合
- 如果查询涉及逾期，使用 is_overdue = 1 或 overdue_amount > 0
- 响应时间限制：SQL 必须在 5 秒内执行完成

## 输出格式
必须返回 JSON 格式（包含 sql 字段）：
{{"sql": "SELECT ...", "explanation": "这个查询将返回..."}}
"""

RESULT_EXPLAIN_PROMPT = """你是一个专业的财务数据分析助手。根据以下查询结果，用自然语言向用户解释：

查询: {query}
SQL: {sql}
结果: {result}

请用简洁的中文解释结果，并指出关键发现。如果结果为空，也请如实告知用户。
"""


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
        import re

        dangerous_pattern = re.compile(
            r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
            re.IGNORECASE,
        )
        if dangerous_pattern.search(sql):
            return False
        return True

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
                system=SYSTEM_PROMPT,
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
