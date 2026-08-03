"""MCP-сервер для Checko.ru API v2 (MCP Python SDK 2.x).

В SDK 2.x обработчики передаются в конструктор `Server(...)`, а не навешиваются
декораторами, и результат нужно собирать явно (`CallToolResult`, `ListToolsResult`
и т. д.) — автоматической обёртки возвращаемых значений больше нет.

Сервер собирается фабрикой `build_server()`, а не создаётся на уровне модуля:
это позволяет тестам поднимать изолированный экземпляр с подменённым клиентом.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import mcp_types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from . import _shape
from . import prompts as prompts_mod
from . import resources as resources_mod
from ._validation import ValidationError
from .client import CheckoAPIError, CheckoClient
from .tools import TOOLS, TOOLS_BY_NAME

SERVER_NAME = "checko"

ClientFactory = Callable[[], CheckoClient]

# Все инструменты Checko только читают внешний источник: состояние не меняется,
# повторный вызов даёт тот же результат, набор сущностей открытый.
# Агент использует эти подсказки, чтобы не запрашивать подтверждение на каждый вызов.
_READ_ONLY = types.ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)


class _Runtime:
    """Владелец единственного CheckoClient на время жизни сервера."""

    def __init__(self, client_factory: ClientFactory | None = None) -> None:
        self._factory: ClientFactory = client_factory or CheckoClient
        self._client: CheckoClient | None = None

    def client(self) -> CheckoClient:
        if self._client is None:
            self._client = self._factory()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _text(payload: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=payload)]


def _ok(data: dict[str, Any]) -> types.CallToolResult:
    """Успешный результат: человекочитаемый JSON + машиночитаемая копия."""
    return types.CallToolResult(
        content=_text(json.dumps(data, ensure_ascii=False, indent=2)),
        structured_content=data,
        is_error=False,
    )


def _fail(message: str) -> types.CallToolResult:
    """Ошибка выполнения инструмента.

    `is_error=True` обязателен: иначе агент не отличает сбой от полученных данных
    и может принять текст ошибки за содержательный ответ.
    """
    return types.CallToolResult(content=_text(f"Ошибка: {message}"), is_error=True)


def _build_handlers(runtime: _Runtime) -> dict[str, Callable[..., Awaitable[Any]]]:
    async def on_list_tools(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=spec.name,
                    title=spec.title,
                    description=spec.description,
                    input_schema=spec.schema,
                    annotations=_READ_ONLY,
                )
                for spec in TOOLS
            ]
        )

    async def on_call_tool(
        ctx: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        spec = TOOLS_BY_NAME.get(params.name)
        if spec is None:
            return _fail(f"Неизвестный инструмент: {params.name}")

        arguments: dict[str, Any] = dict(params.arguments or {})

        # detail — параметр сервера, в запрос к API он не уходит.
        detail = str(arguments.pop("detail", _shape.COMPACT)).strip().lower()
        if detail not in (_shape.COMPACT, _shape.FULL):
            return _fail(
                f"'detail' должен быть '{_shape.COMPACT}' или '{_shape.FULL}' "
                f"(получено: '{detail}')."
            )

        # Валидация идёт до создания клиента: иначе при отсутствующем API-ключе
        # любая ошибка в аргументах маскируется сообщением про ключ.
        try:
            if spec.pre is not None:
                spec.pre(arguments)
        except ValidationError as exc:
            return _fail(str(exc))

        if arguments.get("source") and detail != _shape.FULL:
            return _fail(
                "source=true возвращает полный исходный набор данных ФНС, и сворачивать "
                'его бессмысленно. Повторите вызов с detail="full" — либо уберите source, '
                "если нужны только основные сведения."
            )

        try:
            client = runtime.client()
            if spec.handler is not None:
                # Каскад сам решает, какие эндпоинты вызвать, и отдаёт готовый результат.
                result = await spec.handler(client, arguments, detail)
            else:
                raw = await client.get(spec.endpoint, **arguments)
                result = _shape.shape(spec.endpoint, raw, detail)
        except (ValidationError, CheckoAPIError) as exc:
            return _fail(str(exc))

        return _ok(result)

    async def on_list_resources(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=resources_mod.list_resources())

    async def on_read_resource(
        ctx: ServerRequestContext[None], params: types.ReadResourceRequestParams
    ) -> types.ReadResourceResult:
        uri = str(params.uri)
        text = resources_mod.read_resource_text(uri)
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(uri=uri, text=text, mime_type="text/markdown")
            ]
        )

    async def on_list_prompts(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListPromptsResult:
        return types.ListPromptsResult(prompts=prompts_mod.list_prompts())

    async def on_get_prompt(
        ctx: ServerRequestContext[None], params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        return prompts_mod.get_prompt(params.name, params.arguments)

    return {
        "on_list_tools": on_list_tools,
        "on_call_tool": on_call_tool,
        "on_list_resources": on_list_resources,
        "on_read_resource": on_read_resource,
        "on_list_prompts": on_list_prompts,
        "on_get_prompt": on_get_prompt,
    }


def build_server(
    client_factory: ClientFactory | None = None,
) -> tuple[Server[None], _Runtime]:
    """Собрать сервер и его runtime.

    `client_factory` подменяется в тестах, чтобы не обращаться к сети
    и не требовать реального API-ключа.
    """
    runtime = _Runtime(client_factory)
    server: Server[None] = Server(
        SERVER_NAME,
        title="Checko — проверка контрагентов",
        instructions=(
            "Инструменты дают доступ к российским государственным реестрам через API "
            "Checko.ru. Перед проверкой физлица ознакомьтесь с ресурсом "
            "checko://docs/legal. Данные о белорусских организациях через это API "
            "недоступны."
        ),
        **_build_handlers(runtime),
    )
    return server, runtime


async def run() -> None:
    server, runtime = build_server()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await runtime.aclose()
