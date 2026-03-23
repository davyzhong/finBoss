import httpx
import urllib.parse
from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class WeComOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    USER_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        cfg = get_settings().wecom_oauth
        params = {
            "appid": cfg.corp_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": "snsapi_userinfo",
            "state": state,
            "agentid": cfg.agent_id,
        }
        query = urllib.parse.urlencode(params)
        url = f"{self.AUTHORIZE_URL}?{query}#wechat_redirect"
        return url, state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().wecom_oauth
        with httpx.Client(timeout=10) as client:
            token_resp = client.get(
                self.TOKEN_URL,
                params={"corpid": cfg.corp_id, "corpsecret": cfg.corp_secret},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")

            user_resp = client.get(
                self.USER_INFO_URL,
                params={"access_token": access_token, "code": code},
            )
            user_resp.raise_for_status()
            return user_resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        return OAuthUserInfo(external_id="", provider="wecom", name="", email="")

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        return OAuthUserInfo(
            external_id=user_data.get("UserId", ""),
            provider="wecom",
            name=user_data.get("name", ""),
            email=user_data.get("email", ""),
        )
