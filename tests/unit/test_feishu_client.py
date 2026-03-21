"""FeishuClient 单元测试"""
import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

import pytest


class TestFeishuClientVerifySignature:
    """verify_signature() 签名验证测试"""

    def test_missing_signature_returns_false(self):
        from services.feishu.feishu_client import FeishuClient

        client = FeishuClient()
        assert client.verify_signature("", "1234567890", b"{}") is False

    def test_no_verification_token_skips_check(self):
        """未配置 verification_token 时跳过验证（返回 True）"""
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.verification_token = ""
            from services.feishu.feishu_client import FeishuClient

            client = FeishuClient()
            # 无 token 配置，即使签名不匹配也返回 True
            assert client.verify_signature("any_signature", "1234567890", b"{}") is True

    def test_valid_signature_passes(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.verification_token = "test_secret"
            mock_config.return_value.app_id = ""
            mock_config.return_value.app_secret = ""
            mock_config.return_value.bot_name = "Bot"

            from services.feishu.feishu_client import FeishuClient

            client = FeishuClient()

            timestamp = "1234567890"
            raw_body = b'{"event": "test"}'
            secret = "test_secret"
            string_to_sign = f"{timestamp}{raw_body.decode()}"
            expected_sign = hmac.new(
                secret.encode(), string_to_sign.encode(), hashlib.sha256
            ).hexdigest()

            result = client.verify_signature(expected_sign, timestamp, raw_body)
            assert result is True

    def test_invalid_signature_fails(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.verification_token = "test_secret"
            mock_config.return_value.app_id = ""
            mock_config.return_value.app_secret = ""
            mock_config.return_value.bot_name = "Bot"

            from services.feishu.feishu_client import FeishuClient

            client = FeishuClient()
            result = client.verify_signature("wrong_signature", "1234567890", b"{}")
            assert result is False


class TestFeishuClientTokenCaching:
    """tenant_access_token 缓存逻辑测试"""

    def test_token_cached_within_expiry(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                # 模拟 token 响应
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.post.return_value.json.return_value = {
                    "tenant_access_token": "token_abc123",
                    "expire": 7200,
                }
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()

                # 第一次调用（获取 token）
                token1 = client._get_tenant_token()
                assert token1 == "token_abc123"

                # 第二次调用（应使用缓存，不发 HTTP 请求）
                token2 = client._get_tenant_token()
                assert token2 == "token_abc123"

                # 只应发起一次 HTTP 请求（第二次从缓存读取）
                assert mock_client.post.call_count == 1

    def test_token_refreshed_when_near_expiry(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.post.return_value.status_code = 200

                call_count = [0]

                def fake_json():
                    call_count[0] += 1
                    return {"tenant_access_token": f"token_{call_count[0]}", "expire": 7200}

                mock_client.post.return_value.json = fake_json
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                # 模拟 token 已过期（当前时间超过过期时间-60s缓冲）
                # 即：time.time() > (_token_expires_at - 60)
                # 设置为 time.time() - 1 确保已过期
                client._token_expires_at = time.time() - 1

                token = client._get_tenant_token()
                # 应刷新 token（因为已过期）
                assert token == "token_1"
                assert call_count[0] == 1


class TestFeishuClientSendMessage:
    """send_message() 测试"""

    def test_send_message_success(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.post.return_value.status_code = 200
                mock_client.post.return_value.json.return_value = {"code": 0, "msg": "success"}
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                result = client.send_message(
                    receive_id="ou_123",
                    msg_type="text",
                    content={"text": "hello"},
                )

                assert result is True

    def test_send_message_failure(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.post.return_value.status_code = 400
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                result = client.send_message(
                    receive_id="ou_123",
                    msg_type="text",
                    content={"text": "hello"},
                )

                assert result is False


class TestFeishuClientSendCard:
    """send_card() 测试"""

    def test_send_card_calls_send_message(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            from services.feishu.feishu_client import FeishuClient

            client = FeishuClient()
            # 直接 mock send_message 以隔离验证 send_card 的参数构造
            with patch.object(client, "send_message", return_value=True) as mock_send:
                card = {"elements": [{"tag": "markdown", "content": "**Hello**"}]}
                result = client.send_card(receive_id="ou_123", card_content=card)

                assert result is True
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                # 验证 receive_id、msg_type、content 参数
                _, kwargs = call_args
                assert kwargs["receive_id"] == "ou_123"
                assert kwargs["msg_type"] == "interactive"
                # card_content 被包装成 zh_cn 结构
                assert "zh_cn" in kwargs["content"]
                assert kwargs["content"]["zh_cn"]["elements"] == card["elements"]


class TestFeishuClientReplyMessage:
    """reply_message() 测试"""

    def test_reply_message_calls_correct_endpoint(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.post.return_value.status_code = 200
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                result = client.reply_message(
                    message_id="om_abc123",
                    msg_type="text",
                    content={"text": "reply"},
                )

                assert result is True
                call_url = mock_client.post.call_args[0][0]
                assert "om_abc123" in call_url
                assert "reply" in call_url


class TestFeishuClientGetUserInfo:
    """get_user_info() 测试"""

    def test_get_user_info_success(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value.status_code = 200
                mock_client.get.return_value.json.return_value = {
                    "data": {
                        "user": {
                            "user_id": "ou_123",
                            "name": "张三",
                            "en_name": "Zhang San",
                        }
                    }
                }
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                result = client.get_user_info(user_id="ou_123")

                assert result["user_id"] == "ou_123"
                assert result["name"] == "张三"

    def test_get_user_info_failure_returns_empty(self):
        with patch("services.feishu.feishu_client.get_feishu_config") as mock_config:
            mock_config.return_value.app_id = "test_app_id"
            mock_config.return_value.app_secret = "test_app_secret"
            mock_config.return_value.bot_name = "Bot"

            with patch("services.feishu.feishu_client.httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value.status_code = 404
                mock_client_cls.return_value = mock_client

                from services.feishu.feishu_client import FeishuClient

                client = FeishuClient()
                result = client.get_user_info(user_id="ou_not_exist")

                assert result == {}
