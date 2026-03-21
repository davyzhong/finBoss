"""飞书事件处理器"""
import asyncio
import json
import logging
from typing import Any

from services.feishu.feishu_client import FeishuClient
from services.feishu.card_builder import CardBuilder
from services.ai.nl_query_service import NLQueryService
from services.ai.attribution_service import AttributionService

logger = logging.getLogger(__name__)


# 内存去重表（生产环境建议用 Redis）
_processed_messages: set[str] = set()
MAX_DEDUP_SIZE = 10000


class EventHandler:
    """飞书事件分发处理器"""

    def __init__(self):
        self.feishu_client = FeishuClient()
        self.card_builder = CardBuilder()
        self.nl_query = NLQueryService()
        self.attribution = AttributionService()

    def _extract_query(self, text: str, bot_name: str) -> str:
        """从用户消息中提取查询内容（去除 @机器人 标记）"""
        text = text.strip()
        # 去除 @机器人名称
        for prefix in [f"@{bot_name}", f"@{bot_name} ", bot_name]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        # 去除首尾标点
        text = text.strip("：:").strip()
        return text

    def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否已处理（幂等去重）"""
        if message_id in _processed_messages:
            return True
        _processed_messages.add(message_id)
        # 防止内存无限增长
        if len(_processed_messages) > MAX_DEDUP_SIZE:
            _processed_messages.clear()
        return False

    async def handle_message(self, event: dict[str, Any]) -> None:
        """处理接收到的消息事件"""
        message_id = event.get("message", {}).get("message_id", "")
        if self._is_duplicate(message_id):
            logger.info(f"Duplicate message ignored: {message_id}")
            return

        sender = event.get("sender", {})
        receive_id = sender.get("sender_id", {}).get("open_id", "")
        message_content = event.get("message", {}).get("content", "{}")

        # 解析消息内容
        try:
            content = json.loads(message_content)
            text = content.get("text", "")
        except Exception:
            text = ""

        query = self._extract_query(text, self.feishu_client.bot_name)
        if not query:
            return

        # 异步处理（飞书要求 3s 内响应）
        asyncio.create_task(self._process_query_async(receive_id, query))

    async def _process_query_async(self, receive_id: str, query: str) -> None:
        """异步处理查询（后台执行，不阻塞 Webhook）"""
        try:
            # 判断是否为归因分析查询
            if any(kw in query for kw in ["为什么", "原因", "导致", "为何"]):
                result = self.attribution.analyze(query)
                card = self.card_builder.attribution_card(
                    {
                        "question": result.question,
                        "factors": [
                            {
                                "dimension": f.dimension,
                                "description": f.description,
                                "confidence": f.confidence,
                                "suggestion": f.suggestion,
                            }
                            for f in result.factors
                        ],
                        "overall_confidence": result.overall_confidence,
                        "analysis_time": result.analysis_time,
                    }
                )
            else:
                nl_result = self.nl_query.query(query)
                card = self.card_builder.query_result_card(query=query, result=nl_result)

            self.feishu_client.send_card(receive_id, card)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            error_card = self.card_builder.error_card(f"处理失败: {str(e)}")
            self.feishu_client.send_card(receive_id, error_card)

    def handle_button_callback(self, callback_data: dict[str, Any]) -> None:
        """处理卡片按钮回调"""
        action = callback_data.get("action", "")

        if action == "retry":
            # 重新处理逻辑（需要存储原始 query）
            pass
        elif action == "view_detail":
            # 查看详情
            pass
        elif action == "trend":
            # 趋势分析
            pass
        elif action == "customer":
            # 客户分析
            pass
