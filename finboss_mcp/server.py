"""FinBoss MCP Server

Usage:
    python -m finboss_mcp.server
    uv run finboss-mcp

注册到 Claude Code:
在 ~/.claude/settings.json 中添加 mcpServers.finboss 配置
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

# 确保项目根目录在路径中（用于导入 services）
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# MCP Server 实例
app = Server("finboss")

# 工具注册表
TOOLS: dict[str, dict[str, Any]] = {}


def _result_json(data: Any, error: str | None = None) -> list[TextContent]:
    """将结果转为 JSON TextContent"""
    content = {"data": data, "error": error}
    return [TextContent(type="text", text=json.dumps(content, ensure_ascii=False, indent=2, default=str))]


# ---------------------------------------------------------------------------
# ClickHouse 工具
# ---------------------------------------------------------------------------

TOOLS["clickhouse_query"] = {
    "description": "在 ClickHouse 中执行只读 SQL 查询并返回结构化结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL 查询语句（仅支持 SELECT）"},
            "params": {"type": "object", "description": "查询参数"},
            "limit": {"type": "integer", "description": "结果条数限制，默认 100，最大 10000"},
        },
        "required": ["sql"],
    },
    "handler": None,  # 动态填充
}


def _register_clickhouse_tools() -> None:
    """延迟注册 ClickHouse 工具，导入时避免循环依赖"""
    from services.clickhouse_service import ClickHouseDataService
    from services.validators import validate_readonly_sql

    async def handle_clickhouse_query(sql: str, params: dict | None = None, limit: int | None = None) -> CallToolResult:
        try:
            # 验证 SQL 安全性
            validate_readonly_sql(sql)

            ch = ClickHouseDataService()
            result = ch.execute_query(sql, params or {}, limit=limit or 100)
            return CallToolResult(content=_result_json(result))
        except Exception as e:
            logger.error(f"clickhouse_query error: {e}")
            return CallToolResult(content=_result_json(None, str(e)), isError=True)

    async def handle_clickhouse_list_tables() -> CallToolResult:
        try:
            ch = ClickHouseDataService()
            tables = ch.list_tables()
            return CallToolResult(content=_result_json(tables))
        except Exception as e:
            logger.error(f"clickhouse_list_tables error: {e}")
            return CallToolResult(content=_result_json(None, str(e)), isError=True)

    TOOLS["clickhouse_query"]["handler"] = handle_clickhouse_query
    TOOLS["clickhouse_list_tables"] = {
        "description": "列出 ClickHouse finboss 数据库中的所有表",
        "input_schema": {"type": "object", "properties": {}},
        "handler": handle_clickhouse_list_tables,
    }


# ---------------------------------------------------------------------------
# Feishu 工具
# ---------------------------------------------------------------------------

async def handle_feishu_send_message(receive_id: str, msg_type: str = "text", content: str = "") -> CallToolResult:
    """发送飞书文本消息"""
    try:
        from services.feishu import FeishuClient

        client = FeishuClient()
        client.send_message(receive_id, msg_type, content)
        return CallToolResult(content=_result_json({"status": "sent", "receive_id": receive_id}))
    except Exception as e:
        logger.error(f"feishu_send_message error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


async def handle_feishu_send_card(receive_id: str, card_json: str) -> CallToolResult:
    """发送飞书卡片消息"""
    try:
        import json as _json

        card = _json.loads(card_json)
        from services.feishu import FeishuClient

        client = FeishuClient()
        client.send_card(receive_id, card)
        return CallToolResult(content=_result_json({"status": "sent", "receive_id": receive_id}))
    except Exception as e:
        logger.error(f"feishu_send_card error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


TOOLS["feishu_send_message"] = {
    "description": "向指定用户或群组发送飞书文本消息",
    "input_schema": {
        "type": "object",
        "properties": {
            "receive_id": {"type": "string", "description": "接收者 ID（open_id / union_id / chat_id）"},
            "msg_type": {"type": "string", "description": "消息类型，默认 text", "default": "text"},
            "content": {"type": "string", "description": "消息内容"},
        },
        "required": ["receive_id", "content"],
    },
    "handler": handle_feishu_send_message,
}

TOOLS["feishu_send_card"] = {
    "description": "向指定用户或群组发送飞书卡片消息",
    "input_schema": {
        "type": "object",
        "properties": {
            "receive_id": {"type": "string", "description": "接收者 ID"},
            "card_json": {"type": "string", "description": "飞书卡片 JSON 字符串"},
        },
        "required": ["receive_id", "card_json"],
    },
    "handler": handle_feishu_send_card,
}


# ---------------------------------------------------------------------------
# RAG 工具
# ---------------------------------------------------------------------------

async def handle_rag_search(query: str, top_k: int = 5, category: str | None = None) -> CallToolResult:
    """搜索知识库"""
    try:
        from services.ai import RAGService

        rag = RAGService()
        results = rag.search(query, top_k=top_k, category=category)
        return CallToolResult(content=_result_json(results))
    except Exception as e:
        logger.error(f"rag_search error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


async def handle_rag_ingest(doc: str, metadata: dict | None = None) -> CallToolResult:
    """写入知识库"""
    try:
        from services.ai import RAGService

        rag = RAGService()
        result = rag.ingest(doc, metadata or {})
        return CallToolResult(content=_result_json({"id": result}))
    except Exception as e:
        logger.error(f"rag_ingest error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


TOOLS["rag_search"] = {
    "description": "在财务知识库中搜索相关内容（基于向量相似度）",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "top_k": {"type": "integer", "description": "返回结果数量，默认 5", "default": 5},
            "category": {"type": "string", "description": "按类别过滤（如 financial_accounting, indicator_definition）"},
        },
        "required": ["query"],
    },
    "handler": handle_rag_search,
}

TOOLS["rag_ingest"] = {
    "description": "向知识库中写入新的文档（会生成向量嵌入）",
    "input_schema": {
        "type": "object",
        "properties": {
            "doc": {"type": "string", "description": "文档内容"},
            "metadata": {"type": "object", "description": "元数据（如 category, source 等）"},
        },
        "required": ["doc"],
    },
    "handler": handle_rag_ingest,
}


# ---------------------------------------------------------------------------
# 告警工具
# ---------------------------------------------------------------------------

async def handle_alert_evaluate(rule_id: str | None = None) -> CallToolResult:
    """触发告警规则评估"""
    try:
        from services.alert_service import AlertService

        service = AlertService()
        if rule_id:
            results = [service.evaluate_rule(rule_id)]
        else:
            results = service.evaluate_all()
        return CallToolResult(content=_result_json(results))
    except Exception as e:
        logger.error(f"alert_evaluate error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


TOOLS["alert_evaluate"] = {
    "description": "评估告警规则并返回触发结果（可指定 rule_id 或评估全部）",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "告警规则 ID（不指定则评估全部规则）"},
        },
    },
    "handler": handle_alert_evaluate,
}


# ---------------------------------------------------------------------------
# 报告工具
# ---------------------------------------------------------------------------

async def handle_report_generate(report_type: str, **kwargs: Any) -> CallToolResult:
    """生成报告（周报/月报）"""
    try:
        from services.report_service import ReportService

        service = ReportService()
        result = service.generate(report_type=report_type, **kwargs)
        return CallToolResult(content=_result_json(result))
    except Exception as e:
        logger.error(f"report_generate error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


TOOLS["report_generate"] = {
    "description": "生成并发送管理报告（weekly/monthly）",
    "input_schema": {
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["weekly", "monthly"],
                "description": "报告类型",
            },
        },
        "required": ["report_type"],
    },
    "handler": handle_report_generate,
}


# ---------------------------------------------------------------------------
# 自然语言查询工具
# ---------------------------------------------------------------------------

async def handle_nl_query(question: str) -> CallToolResult:
    """自然语言查询 - 将问题转换为 SQL 执行并返回自然语言结果"""
    try:
        from services.ai import NLQueryService

        service = NLQueryService()
        result = service.query(question)
        return CallToolResult(content=_result_json(result))
    except Exception as e:
        logger.error(f"nl_query error: {e}")
        return CallToolResult(content=_result_json(None, str(e)), isError=True)


TOOLS["nl_query"] = {
    "description": "用自然语言查询财务数据（如「本月应收总额是多少」），自动转换为 SQL 执行",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "自然语言问题"},
        },
        "required": ["question"],
    },
    "handler": handle_nl_query,
}


# ---------------------------------------------------------------------------
# MCP 路由处理器
# ---------------------------------------------------------------------------

@app.list_tools()
async def handle_list_tools() -> ListToolsResult:
    """返回所有可用工具"""
    return ListToolsResult(
        tools=[
            Tool(
                name=name,
                description=spec["description"],
                inputSchema=spec["input_schema"],
            )
            for name, spec in TOOLS.items()
        ]
    )


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> CallToolResult:
    """处理工具调用"""
    if name not in TOOLS:
        return CallToolResult(
            content=_result_json(None, f"Unknown tool: {name}"),
            isError=True,
        )

    spec = TOOLS[name]
    handler = spec.get("handler")
    if handler is None:
        return CallToolResult(
            content=_result_json(None, f"Tool {name} handler not initialized"),
            isError=True,
        )

    logger.info(f"Calling tool: {name} with args: {arguments}")
    try:
        return await handler(**(arguments or {}))
    except TypeError as e:
        logger.error(f"Tool {name} call error: {e}")
        return CallToolResult(content=_result_json(None, f"参数错误: {e}"), isError=True)


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

async def main() -> None:
    """启动 MCP Server"""
    # 延迟注册 ClickHouse 工具
    _register_clickhouse_tools()

    logger.info("FinBoss MCP Server starting...")

    from mcp.server.models import InitializationOptions
    from mcp.types import NotificationOptions

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="finboss",
                server_version="0.1.0",
                instructions="FinBoss 企业财务AI数据平台 MCP 工具服务器。提供 ClickHouse 查询、飞书消息、RAG 知识库、告警评估、报告生成、自然语言查询等工具。",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
