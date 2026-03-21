"""测试飞书事件处理器"""
import pytest
from unittest.mock import patch, AsyncMock

from services.feishu.event_handler import EventHandler, _processed_messages


class TestEventHandler:
    def setup_method(self):
        self.handler = EventHandler()
        _processed_messages.clear()

    def teardown_method(self):
        _processed_messages.clear()

    def test_extract_query_strips_bot_mention(self):
        query = self.handler._extract_query("@FinBoss财务助手 本月应收总额", "FinBoss财务助手")
        assert query == "本月应收总额"

    def test_extract_query_strips_punctuation(self):
        query = self.handler._extract_query("：本月应收总额", "")
        assert query == "本月应收总额"

    def test_extract_query_empty(self):
        query = self.handler._extract_query("", "Bot")
        assert query == ""

    @pytest.mark.asyncio
    async def test_is_duplicate_new_message(self):
        """新消息返回 False 并注册到去重表"""
        msg_id = "test_msg_123"
        event = {
            "message": {"message_id": msg_id, "content": '{"text":"test"}'},
            "sender": {"sender_id": {"open_id": "user_1"}},
        }
        with patch.object(self.handler, "_process_query_async", new_callable=AsyncMock):
            await self.handler.handle_message(event)
        # 再次发送同一消息应被识别为重复
        assert self.handler._is_duplicate(msg_id) is True

    def test_is_duplicate_unknown_id(self):
        """未知 ID 返回 False，不修改 dedup 表"""
        msg_id = "unknown_msg"
        initial_len = len(_processed_messages)
        result = self.handler._is_duplicate(msg_id)
        assert result is False
        # 不应修改 dedup 表
        assert len(_processed_messages) == initial_len
