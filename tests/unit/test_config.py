from api.config import APIKeyConfig


def test_api_key_config_defaults():
    cfg = APIKeyConfig()
    assert cfg.keys == []
    assert cfg.rate_limit == 100


def test_api_key_config_parses_csv():
    cfg = APIKeyConfig(keys="key1,key2,key3")
    assert cfg.keys == ["key1", "key2", "key3"]


def test_api_key_config_from_env(monkeypatch):
    # pydantic_settings decodes list fields from env as JSON
    monkeypatch.setenv("API_KEYS", '["a", "b"]')
    monkeypatch.setenv("API_RATE_LIMIT", "200")
    cfg = APIKeyConfig()
    assert cfg.keys == ["a", "b"]
    assert cfg.rate_limit == 200
