from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Optional


session_store: dict[str, dict] = {}


class InMemorySessionStore:
    """内存 Session 存储（开发用，生产换 Redis）"""

    def create(self, user_info: dict, ttl_hours: int = 8) -> str:
        session_id = token_urlsafe(32)
        session_store[session_id] = {
            **user_info,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=ttl_hours),
        }
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        session = session_store.get(session_id)
        if session and session["expires_at"] > datetime.utcnow():
            return session
        session_store.pop(session_id, None)
        return None

    def delete(self, session_id: str) -> None:
        session_store.pop(session_id, None)


class SessionStore:
    """SessionStore 接口（供类型注解使用）"""

    def create(self, user_info: dict, ttl_hours: int = 8) -> str:
        ...

    def get(self, session_id: str) -> Optional[dict]:
        ...

    def delete(self, session_id: str) -> None:
        ...
