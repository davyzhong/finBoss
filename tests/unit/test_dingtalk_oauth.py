from unittest.mock import patch, MagicMock
from services.auth_provider.dingtalk_oauth import DingTalkOAuthProvider


def test_get_authorization_url():
    with patch("services.auth_provider.dingtalk_oauth.get_settings") as mock:
        mock.return_value.dingtalk_oauth.app_id = "ding_app"
        mock.return_value.dingtalk_oauth.redirect_uri = "http://test/callback"
        provider = DingTalkOAuthProvider()
        url, state = provider.get_authorization_url("mystate")
        assert "oapi.dingtalk.com/connect/qrconnect" in url
        assert "appid=ding_app" in url
        assert "state=mystate" in url


def test_parse_user_info():
    provider = DingTalkOAuthProvider()
    result = provider._parse_user_info(
        {},
        {"errcode": 0, "errmsg": "ok", "user_info": {"nick": "李四", "openid": "open_123"}},
    )
    assert result["external_id"] == "open_123"
    assert result["name"] == "李四"
    assert result["provider"] == "dingtalk"
