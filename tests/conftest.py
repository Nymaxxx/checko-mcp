"""Общие фикстуры для тестов."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
import httpx2 as httpx
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from checko_mcp.client import CheckoClient
from checko_mcp.server import build_server

OK_PAYLOAD: dict[str, Any] = {
    "data": {"НаимСокр": 'ООО «Тестовая Компания»'},
    "meta": {"status": "ok", "today_request_count": 1, "balance": 500.0},
}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKO_API_KEY", "test-key")
    monkeypatch.setenv("CHECKO_BASE_URL", "https://api.checko.test/v2")
    monkeypatch.delenv("CHECKO_TIMEOUT", raising=False)
    monkeypatch.delenv("CHECKO_RETRIES", raising=False)


@pytest.fixture
async def make_client() -> AsyncIterator[Callable[..., CheckoClient]]:
    """Фабрика клиента с подменённым транспортом. Закрывает все клиенты после теста."""
    created: list[CheckoClient] = []

    def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> CheckoClient:
        # backoff=0 — пауз между повторами в тестах быть не должно.
        client = CheckoClient(transport=httpx.MockTransport(handler), backoff=0)
        created.append(client)
        return client

    yield _factory

    for client in created:
        await client.aclose()


class Wire:
    """Перехваченный исходящий HTTP-запрос к Checko API."""

    def __init__(self) -> None:
        self.path: str | None = None
        self.params: dict[str, str] = {}
        self.calls: int = 0


@asynccontextmanager
async def mcp_session(
    payload: dict[str, Any] | None = None,
    status: int = 200,
    client_factory: Callable[[], CheckoClient] | None = None,
) -> AsyncIterator[tuple[ClientSession, Wire]]:
    """Поднять сервер и подключить к нему настоящую MCP-сессию в памяти.

    Проверяет весь путь целиком: хендшейк протокола, обработчики сервера,
    пред-валидацию, сборку запроса и разбор ответа. Именно этого слоя не хватало —
    unit-тесты реестров не замечали ни мажорного апгрейда SDK, ни неверных имён
    query-параметров.
    """
    wire = Wire()

    def handler(request: httpx.Request) -> httpx.Response:
        wire.path = request.url.path
        wire.params = dict(request.url.params)
        wire.calls += 1
        return httpx.Response(status, json=payload if payload is not None else OK_PAYLOAD)

    factory = client_factory or (
        lambda: CheckoClient(transport=httpx.MockTransport(handler), backoff=0)
    )
    server, runtime = build_server(client_factory=factory)

    try:
        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    server.run,
                    server_read,
                    server_write,
                    server.create_initialization_options(),
                )
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    yield session, wire
                tg.cancel_scope.cancel()
    finally:
        await runtime.aclose()
