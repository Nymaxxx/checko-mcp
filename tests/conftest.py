"""Общие фикстуры для тестов."""

import httpx
import pytest

from checko_mcp.client import CheckoClient


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKO_API_KEY", "test-key")
    monkeypatch.setenv("CHECKO_BASE_URL", "https://api.checko.test/v2")
    monkeypatch.delenv("CHECKO_TIMEOUT", raising=False)


@pytest.fixture
async def make_client():
    """Фабрика клиента с подменённым httpx-транспортом. Закрывает все клиенты после теста."""
    created: list[CheckoClient] = []

    def _factory(handler):
        transport = httpx.MockTransport(handler)
        client = CheckoClient(transport=transport)
        created.append(client)
        return client

    yield _factory

    for client in created:
        await client.aclose()
