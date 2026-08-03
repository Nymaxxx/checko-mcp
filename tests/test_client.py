"""Тесты для CheckoClient."""

import json

import httpx2 as httpx
import pytest

from checko_mcp.client import CheckoAPIError, CheckoClient


async def test_successful_request_adds_key(make_client):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        captured["user_agent"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"meta": {"status": "ok"}, "data": {"name": "ok"}})

    client = make_client(handler)
    result = await client.get("/company", inn="1234567890")

    assert result["data"]["name"] == "ok"
    assert captured["params"]["key"] == "test-key"
    assert captured["params"]["inn"] == "1234567890"
    assert captured["user_agent"].startswith("checko-mcp/")


async def test_none_params_filtered(make_client):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"meta": {"status": "ok"}})

    client = make_client(handler)
    await client.get("/company", ogrn="1234567890123", inn=None, source=None)

    assert "inn" not in captured["params"]
    assert "source" not in captured["params"]
    assert captured["params"]["ogrn"] == "1234567890123"


async def test_meta_error_raises(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"status": "error", "message": "Лимит запросов исчерпан"}},
        )

    client = make_client(handler)
    with pytest.raises(CheckoAPIError, match="Лимит"):
        await client.get("/company", inn="1234567890")


async def test_http_error_wrapped(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    client = make_client(handler)
    with pytest.raises(CheckoAPIError, match="HTTP 403"):
        await client.get("/company", inn="1234567890")


async def test_invalid_json_wrapped(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    client = make_client(handler)
    with pytest.raises(CheckoAPIError, match="JSON"):
        await client.get("/company", inn="1234567890")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv("CHECKO_API_KEY", "")
    with pytest.raises(CheckoAPIError, match="API-ключ"):
        CheckoClient()


async def test_aclose_does_not_raise(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"status": "ok"}})

    client = make_client(handler)
    await client.get("/company", inn="1234567890")
    await client.aclose()


async def test_request_serialises_payload(make_client):
    payload = {"meta": {"status": "ok", "balance": 1500.5}, "data": {"a": 1}}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps(payload), headers={"content-type": "application/json"}
        )

    client = make_client(handler)
    result = await client.get("/company", inn="1234567890")
    assert result == payload


class TestRetry:
    async def test_retries_on_429_then_succeeds(self, make_client):
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(200, json={"meta": {"status": "ok"}, "data": {}})

        client = make_client(handler)
        await client.get("/company", inn="1234567890")
        assert calls["n"] == 3

    async def test_retries_on_503_then_gives_up(self, make_client):
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503, text="Service Unavailable")

        client = make_client(handler)
        with pytest.raises(CheckoAPIError, match="попыток: 3"):
            await client.get("/company", inn="1234567890")
        assert calls["n"] == 3

    async def test_does_not_retry_client_errors(self, make_client):
        """403 — не временный сбой: повторять его значит зря тратить квоту."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(403, text="Forbidden")

        client = make_client(handler)
        with pytest.raises(CheckoAPIError):
            await client.get("/company", inn="1234567890")
        assert calls["n"] == 1

    async def test_quota_message_is_explicit_on_429(self, make_client):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="")

        client = make_client(handler)
        with pytest.raises(CheckoAPIError, match="лимит запросов"):
            await client.get("/company", inn="1234567890")

    async def test_retry_count_configurable(self, make_client, monkeypatch):
        monkeypatch.setenv("CHECKO_RETRIES", "1")
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503)

        client = make_client(handler)
        with pytest.raises(CheckoAPIError):
            await client.get("/company", inn="1234567890")
        assert calls["n"] == 1


class TestErrorText:
    async def test_network_error_message_is_never_empty(self, make_client):
        """str() части сетевых ошибок httpx пуст — агент не должен получать «Ошибка: »."""

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("")

        client = make_client(handler)
        with pytest.raises(CheckoAPIError) as exc_info:
            await client.get("/company", inn="1234567890")

        message = str(exc_info.value)
        assert "ConnectError" in message
        assert not message.rstrip().endswith(":")

    async def test_api_key_never_leaks_into_error(self, make_client):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = make_client(handler)
        with pytest.raises(CheckoAPIError) as exc_info:
            await client.get("/company", inn="1234567890")
        assert "test-key" not in str(exc_info.value)


class TestBalance:
    async def test_balance_recorded_from_meta(self, make_client):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"meta": {"status": "ok", "balance": 42.5}})

        client = make_client(handler)
        assert client.last_balance is None
        await client.get("/company", inn="1234567890")
        assert client.last_balance == 42.5

    async def test_missing_balance_leaves_none(self, make_client):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"meta": {"status": "ok"}})

        client = make_client(handler)
        await client.get("/company", inn="1234567890")
        assert client.last_balance is None
