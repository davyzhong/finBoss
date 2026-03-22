import pytest
from api.config import APIKeyConfig


def test_api_key_config_defaults():
    cfg = APIKeyConfig()
    assert cfg.keys == []
    assert cfg.rate_limit == 100


def test_api_key_config_parses_csv():
    cfg = APIKeyConfig(keys="key1,key2,key3")
    assert cfg.keys == ["key1", "key2", "key3"]


def test_api_key_config_accepts_list():
    cfg = APIKeyConfig(keys=["a", "b"])
    assert cfg.keys == ["a", "b"]


def test_api_key_config_rate_limit_override():
    cfg = APIKeyConfig(rate_limit=500)
    assert cfg.rate_limit == 500
