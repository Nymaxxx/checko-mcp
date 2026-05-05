"""MCP-сервер для Checko.ru API v2."""

import json
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from . import prompts as prompts_mod
from . import resources as resources_mod
from ._validation import ValidationError
from .client import CheckoAPIError, CheckoClient
from .tools import TOOLS, TOOLS_BY_NAME

app = Server("checko")

_client: CheckoClient | None = None


def _get_client() -> CheckoClient:
    global _client
    if _client is None:
        _client = CheckoClient()
    return _client


def _json(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _error(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=f"Ошибка: {message}")]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=t.name, description=t.description, inputSchema=t.schema)
        for t in TOOLS
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return _error(f"Неизвестный инструмент: {name}")

    try:
        client = _get_client()
        if spec.pre is not None:
            spec.pre(arguments)
        result = await client.get(spec.endpoint, **arguments)
    except ValidationError as exc:
        return _error(str(exc))
    except CheckoAPIError as exc:
        return _error(str(exc))

    return _json(result)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@app.list_resources()
async def list_resources() -> list[types.Resource]:
    return resources_mod.list_resources()


@app.read_resource()
async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
    text = resources_mod.read_resource_text(str(uri))
    return [ReadResourceContents(content=text, mime_type="text/markdown")]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@app.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    return prompts_mod.list_prompts()


@app.get_prompt()
async def get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    return prompts_mod.get_prompt(name, arguments)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run() -> None:
    global _client
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        if _client is not None:
            await _client.aclose()
            _client = None
