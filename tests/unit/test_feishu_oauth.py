from unittest.mock import patch, MagicMock
import pytest
from services.auth_provider.feishu_oauth import FeishuOAuthProvider


def test_get_authorization_url_returns_redirect_url():
    with patch("services.auth_provider.feishu_oauth.get_settings") as mock_settings:
        mock_settings.return_value.feishu_oauth.app_id = "cli_test"
        mock_settings.return_value.feishu_oauth.redirect_uri = "http://test/callback"
        mock_settings.return_value.feishu_oauth.scope = "contact:user.email:readonly"
        provider = FeishuOAuthProvider()
        url, state = provider.get_authorization_url()
        assert url.startswith("https://open.feishu.cn/open-apis/authen/v1/authorize")
        assert "app_id=cli_test" in url
        assert len(state) > 10


def test_exchange_code_raises_on_feishu_error():
    with patch("services.auth_provider.feishu_oauth.get_settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.app_id = "cli_test"
        mock_cfg.app_secret = "secret"
        mock_settings.return_value.feishu_oauth = mock_cfg
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            error_resp = MagicMock()
            error_resp.json.return_value = {"code": 99991663, "msg": "invalid code"}
            error_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = error_resp
            mock_client_cls.return_value = mock_client
            provider = FeishuOAuthProvider()
            with pytest.raises(Exception) as exc_info:
                provider.exchange_code("bad_code")
            assert "99991663" in str(exc_info.value) or "invalid code" in str(exc_info.value)


def test_get_user_info_parses_response():
    provider = FeishuOAuthProvider()
    token_data = {"access_token": "test_token", "expires_in": 7200}
    user_data = {
        "data": {
            "user_id": "ou_test",
            "name": "张三",
            "email": "zhangsan@test.com",
        }
    }
    result = provider._parse_user_info(token_data, user_data)
    assert result["external_id"] == "ou_test"
    assert result["name"] == "张三"
    assert result["email"] == "zhangsan@test.com"
    assert result["provider"] == "feishu"
