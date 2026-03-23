import pytest
import time
from services.session_service import SessionStore, InMemorySessionStore


def test_create_returns_session_id():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1", "role": "admin"})
    assert isinstance(sid, str)
    assert len(sid) > 20


def test_get_returns_user_info():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1", "role": "admin", "name": "张三"})
    result = store.get(sid)
    assert result["user_id"] == "u1"
    assert result["role"] == "admin"
    assert result["name"] == "张三"


def test_get_expired_returns_none():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1"}, ttl_hours=0)  # expires immediately
    time.sleep(0.1)
    assert store.get(sid) is None


def test_delete_removes_session():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1"})
    store.delete(sid)
    assert store.get(sid) is None


def test_get_unknown_returns_none():
    store = InMemorySessionStore()
    assert store.get("unknown-id") is None
