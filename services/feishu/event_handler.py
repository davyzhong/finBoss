"""飞书事件处理器"""
import asyncio
import json
import logging
from collections import OrderedDict
from typing import Any

from services.ai.attribution_service import AttributionService
from services.ai.nl_query_service import NLQueryService
from services.feishu.card_builder import CardBuilder
from services.feishu.feishu_client import FeishuClient

logger = logging.getLogger(__name__)

# LRU 去重表（OrderedDict 实现 FIFO 淘汰，超容量时只移除最旧的条目）
# 生产环境建议替换为 Redis（支持跨 worker 共享 + TTL 过期）
_MAX_DEDUP_SIZE = 10000
# message_id -> (query, receive_id)
_processed_messages: OrderedDict[str, tuple[str, str]] = OrderedDict()


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
        """检查消息是否已处理（幂等去重）。

        注意：此方法仅检查，不修改状态。状态写入由 handle_message 负责。
        """
        if message_id in _processed_messages:
            # 已存在：移至末尾（更新访问顺序），返回 True
            _processed_messages.move_to_end(message_id)
            return True
        # 新消息：容量超限时移除最旧的条目
        if len(_processed_messages) >= _MAX_DEDUP_SIZE:
            _processed_messages.popitem(last=False)
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

        # 记录原始 query 和 receive_id（按钮回调需要用到）
        _processed_messages[message_id] = (query, receive_id)

        # 异步处理（飞书要求 3s 内响应）
        asyncio.create_task(self._process_query_async(receive_id, query, message_id))

    async def _process_query_async(
        self, receive_id: str, query: str, message_id: str = ""
    ) -> None:
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
        """处理卡片按钮回调。

        Args:
            callback_data: 飞书卡片回调数据，应包含 action 和 message_id
        """
        action = callback_data.get("action", "")
        message_id = callback_data.get("message_id", "")
        # 从去重表中恢复原始 query 和 receive_id（若已被淘汰则返回 None）
        stored = _processed_messages.get(message_id)
        original_query = stored[0] if stored else None
        receive_id = stored[1] if stored else callback_data.get("receive_id", "")

        if action == "retry":
            if original_query:
                logger.info(f"Retrying query for message {message_id}: {original_query}")
                self._send_card_for_query(original_query, receive_id)
            else:
                error_card = self.card_builder.error_card("原始查询已过期，请重新发起查询")
                if receive_id:
                    self.feishu_client.send_card(receive_id, error_card)

        elif action == "view_detail":
            if original_query:
                self._send_detail_card(original_query, receive_id)

        elif action == "trend":
            if original_query:
                trend_query = f"{original_query} 近30天趋势"
                self._send_card_for_query(trend_query, receive_id)

        elif action == "customer":
            if original_query:
                customer_query = f"客户维度分析：{original_query}"
                self._send_card_for_query(customer_query, receive_id)

        else:
            logger.warning(f"Unknown button action: {action}")

    def _send_card_for_query(self, query: str, receive_id: str) -> None:
        """根据 query 内容生成并发送卡片（同步封装）"""
        try:
            if any(kw in query for kw in ["为什么", "原因", "导致", "为何"]):
                result = self.attribution.analyze(query)
                card = self.card_builder.attribution_card({
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
                })
            else:
                nl_result = self.nl_query.query(query)
                card = self.card_builder.query_result_card(query=query, result=nl_result)

            if receive_id:
                self.feishu_client.send_card(receive_id, card)
        except Exception as e:
            logger.error(f"Error in _send_card_for_query: {e}")

    def _send_detail_card(self, query: str, receive_id: str) -> None:
        """发送详情卡片（带更大 limit）"""
        try:
            nl_result = self.nl_query.query(query)
            card = self.card_builder.query_result_card(query=f"{query} (详情)", result=nl_result)
            if receive_id:
                self.feishu_client.send_card(receive_id, card)
        except Exception as e:
            logger.error(f"Error in _send_detail_card: {e}")
