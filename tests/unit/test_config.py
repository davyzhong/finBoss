import os

import pytest
from api.config import APIKeyConfig

# Ensure test env var does not leak into these isolated tests
_original_keys = os.environ.pop("API_KEYS", None)


def test_api_key_config_defaults():
    cfg = APIKeyConfig()
    assert cfg.keys == []
    assert cfg.rate_limit == 100


def test_api_key_config_parses_csv():
    cfg = APIKeyConfig(keys_str="key1,key2,key3")
    assert cfg.keys == ["key1", "key2", "key3"]


def test_api_key_config_accepts_list():
    cfg = APIKeyConfig(keys_str="a,b")
    assert cfg.keys == ["a", "b"]


def test_api_key_config_rate_limit_override():
    cfg = APIKeyConfig(rate_limit=500)
    assert cfg.rate_limit == 500


# Restore original env var after tests
if _original_keys is not None:
    os.environ["API_KEYS"] = _original_keys
