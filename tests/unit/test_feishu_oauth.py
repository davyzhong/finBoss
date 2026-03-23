from unittest.mock import patch, MagicMock
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
