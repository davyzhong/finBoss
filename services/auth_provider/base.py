from abc import ABC, abstractmethod
from typing import TypedDict


class OAuthUserInfo(TypedDict):
    external_id: str
    provider: str
    name: str
    email: str


class OAuthProvider(ABC):
    @abstractmethod
    def get_authorization_url(self, state: str) -> tuple[str, str]:
        """返回 (authorization_url, state)"""
        ...

    @abstractmethod
    def exchange_code(self, code: str) -> dict:
        """用 code 换取 access_token"""
        ...

    @abstractmethod
    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """用 access_token 获取用户信息"""
        ...
