import httpx
import urllib.parse
from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class DingTalkOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://oapi.dingtalk.com/connect/qrconnect"
    TOKEN_URL = "https://oapi.dingtalk.com/sns/gettoken"
    USER_INFO_URL = "https://oapi.dingtalk.com/sns/getuserinfo_bycode"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        cfg = get_settings().dingtalk_oauth
        params = {
            "appid": cfg.app_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": "openid",
            "state": state,
            "response_type": "code",
        }
        query = urllib.parse.urlencode(params)
        return f"{self.AUTHORIZE_URL}?{query}", state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().dingtalk_oauth
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self.TOKEN_URL,
                json={"appkey": cfg.app_id, "appsecret": cfg.app_secret},
            )
            resp.raise_for_status()
            token_data = resp.json()
            access_token = token_data.get("access_token", "")

            user_resp = client.post(
                self.USER_INFO_URL,
                json={"access_token": access_token, "code": code},
            )
            user_resp.raise_for_status()
            return user_resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        return OAuthUserInfo(external_id="", provider="dingtalk", name="", email="")

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        info = user_data.get("user_info", {})
        return OAuthUserInfo(
            external_id=info.get("openid", ""),
            provider="dingtalk",
            name=info.get("nick", ""),
            email="",
        )
