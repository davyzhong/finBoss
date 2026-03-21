"""测试飞书事件处理器"""
import pytest
from unittest.mock import MagicMock, patch
from services.feishu.event_handler import EventHandler


class TestEventHandler:
    def setup_method(self):
        self.handler = EventHandler()

    def test_extract_query_strips_bot_mention(self):
        query = self.handler._extract_query("@FinBoss财务助手 本月应收总额", "FinBoss财务助手")
        assert query == "本月应收总额"

    def test_extract_query_strips_punctuation(self):
        query = self.handler._extract_query("：本月应收总额", "")
        assert query == "本月应收总额"

    def test_extract_query_empty(self):
        query = self.handler._extract_query("", "Bot")
        assert query == ""

    def test_is_duplicate(self):
        msg_id = "test_msg_123"
        assert self.handler._is_duplicate(msg_id) is False
        assert self.handler._is_duplicate(msg_id) is True  # Second call

    def test_is_duplicate_after_clear(self):
        handler = EventHandler()
        msg_id = "fresh_msg"
        assert handler._is_duplicate(msg_id) is False
