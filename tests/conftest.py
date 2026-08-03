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
    # Кэш по умолчанию выключен: иначе повторный запрос в тесте не дойдёт
    # до транспорта и подсчёт обращений станет непредсказуемым.
    # Тесты кэша включают его сами.
    monkeypatch.setenv("CHECKO_CACHE_TTL", "0")


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
    """Перехваченные исходящие HTTP-запросы к Checko API.

    Каскадные инструменты делают несколько запросов, поэтому сохраняется вся
    последовательность, а `path` и `params` указывают на последний запрос.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []

    def record(self, path: str, params: dict[str, str]) -> None:
        self.requests.append((path, params))

    @property
    def calls(self) -> int:
        return len(self.requests)

    @property
    def path(self) -> str | None:
        return self.requests[-1][0] if self.requests else None

    @property
    def params(self) -> dict[str, str]:
        return self.requests[-1][1] if self.requests else {}

    @property
    def paths(self) -> list[str]:
        return [path for path, _ in self.requests]


@asynccontextmanager
async def mcp_session(
    payload: dict[str, Any] | Callable[[httpx.Request], dict[str, Any]] | None = None,
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
        wire.record(request.url.path, dict(request.url.params))
        if callable(payload):
            return httpx.Response(status, json=payload(request))
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
