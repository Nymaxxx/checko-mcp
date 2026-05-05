"""Тесты для CheckoClient."""

import json

import httpx
import pytest

from checko_mcp.client import CheckoAPIError, CheckoClient


@pytest.mark.asyncio
async def test_successful_request_adds_key(make_client):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"meta": {"status": "ok"}, "data": {"name": "ok"}})

    client = make_client(handler)
    result = await client.get("/company", inn="1234567890")

    assert result["data"]["name"] == "ok"
    assert captured["params"]["key"] == "test-key"
    assert captured["params"]["inn"] == "1234567890"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_meta_error_raises(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"status": "error", "message": "Лимит запросов исчерпан"}},
        )

    client = make_client(handler)
    with pytest.raises(CheckoAPIError, match="Лимит"):
        await client.get("/company", inn="1234567890")


@pytest.mark.asyncio
async def test_http_error_wrapped(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    client = make_client(handler)
    with pytest.raises(CheckoAPIError, match="HTTP 403"):
        await client.get("/company", inn="1234567890")


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_aclose_does_not_raise(make_client):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"status": "ok"}})

    client = make_client(handler)
    await client.get("/company", inn="1234567890")
    await client.aclose()


@pytest.mark.asyncio
async def test_request_serialises_payload(make_client):
    """Sanity-check: тело JSON-ответа парсится в dict."""
    payload = {"meta": {"status": "ok", "balance": 1500.5}, "data": {"a": 1}}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps(payload), headers={"content-type": "application/json"}
        )

    client = make_client(handler)
    result = await client.get("/company", inn="1234567890")
    assert result == payload
