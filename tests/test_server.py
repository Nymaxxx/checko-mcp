"""Тесты MCP-слоя: настоящий протокол, настоящий хендшейк.

До появления этих тестов `server.py` был покрыт на 0 %: unit-тесты реестров
проходили даже тогда, когда сервер вообще не поднимался. Именно так мажорный
апгрейд SDK прошёл CI незамеченным, а опубликованный пакет падал при импорте.
"""

import pytest

from checko_mcp import __version__
from checko_mcp.client import CheckoAPIError
from checko_mcp.prompts import PROMPTS
from checko_mcp.resources import RESOURCES
from checko_mcp.server import build_server
from checko_mcp.tools import TOOLS

from .conftest import mcp_session


class TestHandshake:
    async def test_server_initializes(self) -> None:
        async with mcp_session() as (session, _wire):
            tools = await session.list_tools()
        assert tools.tools

    def test_handshake_reports_package_version(self) -> None:
        """Версия в server_info — то, по чему клиент отличает сборки.

        SDK по умолчанию подставляет пустую строку, и её отсутствие ничего
        не ломает: сервер поднимается, инструменты работают. Поэтому потерю
        версии заметит только этот тест.
        """
        server, _runtime = build_server()
        options = server.create_initialization_options()

        assert options.server_version == __version__
        assert options.server_name == "checko"


class TestListTools:
    async def test_exposes_every_registered_tool(self) -> None:
        async with mcp_session() as (session, _wire):
            result = await session.list_tools()
        assert {t.name for t in result.tools} == {spec.name for spec in TOOLS}

    async def test_tools_carry_schema_title_and_annotations(self) -> None:
        async with mcp_session() as (session, _wire):
            result = await session.list_tools()

        for tool in result.tools:
            assert tool.input_schema["type"] == "object"
            assert tool.title
            assert tool.description
            # Подсказки нужны агенту, чтобы не спрашивать подтверждение
            # на каждый read-only вызов.
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False


class TestCallTool:
    async def test_success_returns_structured_content(self) -> None:
        payload = {"data": {"НаимСокр": "ООО «Тест»"}, "meta": {"status": "ok"}}
        async with mcp_session(payload=payload) as (session, _wire):
            result = await session.call_tool("profile", {"identifier": "1234567890123"})

        assert result.is_error is False
        assert result.structured_content["data"] == payload["data"]
        assert "ООО «Тест»" in result.content[0].text

    async def test_unknown_tool_is_reported_as_error(self) -> None:
        async with mcp_session() as (session, _wire):
            result = await session.call_tool("get_nothing", {})

        assert result.is_error is True
        assert "Неизвестный инструмент" in result.content[0].text

    async def test_validation_error_sets_is_error(self) -> None:
        """Агент должен отличать сбой от данных — иначе примет текст ошибки за ответ."""
        async with mcp_session() as (session, wire):
            result = await session.call_tool("get_bank", {"bic": "abc"})

        assert result.is_error is True
        assert "должен содержать ровно 9 цифр" in result.content[0].text
        assert wire.calls == 0, "невалидный вызов не должен расходовать квоту API"

    async def test_missing_identifier_does_not_reach_api(self) -> None:
        async with mcp_session() as (session, wire):
            result = await session.call_tool("profile", {})

        assert result.is_error is True
        assert wire.calls == 0

    async def test_api_error_sets_is_error(self) -> None:
        payload = {"meta": {"status": "error", "message": "Организация не найдена"}}
        async with mcp_session(payload=payload) as (session, _wire):
            result = await session.call_tool("profile", {"identifier": "1234567890123"})

        assert result.is_error is True
        assert "Организация не найдена" in result.content[0].text

    async def test_validation_runs_before_client_creation(self) -> None:
        """Без API-ключа ошибка в аргументах не должна маскироваться ошибкой ключа."""

        def broken_factory():
            raise CheckoAPIError("Не задан API-ключ.")

        async with mcp_session(client_factory=broken_factory) as (session, _wire):
            result = await session.call_tool("get_bank", {"bic": "abc"})

        assert result.is_error is True
        assert "9 цифр" in result.content[0].text
        assert "API-ключ" not in result.content[0].text


class TestResources:
    async def test_lists_and_reads_every_resource(self) -> None:
        async with mcp_session() as (session, _wire):
            listing = await session.list_resources()
            assert {str(r.uri) for r in listing.resources} == {r.uri for r in RESOURCES}

            for resource in listing.resources:
                contents = await session.read_resource(resource.uri)
                text = "".join(c.text for c in contents.contents if hasattr(c, "text"))
                assert len(text) > 100, f"ресурс {resource.uri} подозрительно пуст"


class TestPrompts:
    async def test_lists_every_prompt(self) -> None:
        async with mcp_session() as (session, _wire):
            result = await session.list_prompts()
        assert {p.name for p in result.prompts} == {spec.name for spec in PROMPTS}

    async def test_get_prompt_renders_arguments(self) -> None:
        async with mcp_session() as (session, _wire):
            result = await session.get_prompt(
                "check_counterparty", {"query": "ООО «Тестовая Компания»"}
            )

        text = result.messages[0].content.text
        assert "ООО «Тестовая Компания»" in text
        assert len(text) > 200

    async def test_missing_required_argument_raises(self) -> None:
        async with mcp_session() as (session, _wire):
            with pytest.raises(Exception, match="ogrn_or_inn|Отсутствует"):
                await session.get_prompt("analyze_finances", {})
