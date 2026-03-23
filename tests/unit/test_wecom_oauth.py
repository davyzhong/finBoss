from unittest.mock import patch
from services.auth_provider.wecom_oauth import WeComOAuthProvider


def test_get_authorization_url():
    with patch("services.auth_provider.wecom_oauth.get_settings") as mock:
        mock.return_value.wecom_oauth.corp_id = "ww_test"
        mock.return_value.wecom_oauth.agent_id = "100000"
        mock.return_value.wecom_oauth.redirect_uri = "http://test/callback"
        provider = WeComOAuthProvider()
        url, state = provider.get_authorization_url("mystate")
        assert "open.weixin.qq.com/connect/oauth2/authorize" in url
        assert "appid=ww_test" in url
        assert "agentid=100000" in url
        assert "#wechat_redirect" in url


def test_parse_user_info():
    provider = WeComOAuthProvider()
    result = provider._parse_user_info(
        {},
        {"UserId": "wecom_user", "name": "王五", "email": "wang@test.com"},
    )
    assert result["external_id"] == "wecom_user"
    assert result["name"] == "王五"
    assert result["provider"] == "wecom"
