import httpx
import urllib.parse
import base64

from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class FeishuOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/authorize"
    TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token"
    USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        import secrets
        if not state:
            state = secrets.token_urlsafe(16)
        cfg = get_settings().feishu_oauth
        params = {
            "app_id": cfg.app_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": cfg.scope,
            "state": state,
        }
        query = urllib.parse.urlencode(params)
        url = f"{self.AUTHORIZE_URL}?{query}"
        return url, state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().feishu_oauth
        credentials = base64.b64encode(f"{cfg.app_id}:{cfg.app_secret}".encode()).decode()
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
                json={"grant_type": "authorization_code", "code": code},
            )
            resp.raise_for_status()
            return resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_user_info({"access_token": access_token}, data)

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        d = user_data.get("data", {})
        return OAuthUserInfo(
            external_id=d.get("user_id", ""),
            provider="feishu",
            name=d.get("name", ""),
            email=d.get("email", ""),
        )
