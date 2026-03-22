from api.middleware.rate_limit import check_rate_limit, windows


def test_first_request_allowed():
    windows.clear()
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is True


def test_within_limit_allowed():
    windows.clear()
    check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is True


def test_over_limit_rejected():
    windows.clear()
    for _ in range(3):
        check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is False


def test_different_ips_independent():
    windows.clear()
    check_rate_limit("1.1.1.1", "/test", limit=1, window=60)
    result = check_rate_limit("2.2.2.2", "/test", limit=1, window=60)
    assert result is True


def test_different_endpoints_independent():
    windows.clear()
    check_rate_limit("1.1.1.1", "/a", limit=1, window=60)
    result = check_rate_limit("1.1.1.1", "/b", limit=1, window=60)
    assert result is True
