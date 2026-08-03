"""Контракт с Checko API: имена параметров и фактически уходящий запрос.

Этих тестов не хватало больше всего. Реестр инструментов можно покрыть на 100 %
и всё равно отправлять в API параметр, которого у метода нет: так `/entrepreneur`
получал `ogrnip` вместо `ogrn` и не находил предпринимателя, а `/search` принимал
`date_from`, которого у метода не существует, и молча возвращал невыборку.

`API_PARAMS` — список параметров каждого метода по документации Checko API 2.4
(`https://checko.ru/integration/api/<метод>`). При обновлении API правится здесь.
"""

import pytest

from checko_mcp.tools import (
    CLIENT_ONLY_PARAMS,
    HANDLER_ENDPOINTS,
    TOOLS,
    TOOLS_BY_NAME,
)

from .conftest import mcp_session

# Инструменты-обёртки над одним методом API — только для них схема сверяется
# со списком документированных параметров. Каскады сами собирают запросы.
ENDPOINT_TOOLS = [spec for spec in TOOLS if spec.endpoint is not None]
HANDLER_TOOLS = [spec for spec in TOOLS if spec.handler is not None]

# key добавляется клиентом автоматически и в схемах инструментов не участвует.
API_PARAMS: dict[str, set[str]] = {
    "/search": {"by", "obj", "query", "region", "okved", "opf", "active", "codes", "limit", "page"},
    "/company": {"ogrn", "inn", "okpo", "source"},
    "/entrepreneur": {"ogrn", "inn", "okpo", "source"},
    "/person": {"inn"},
    "/finances": {"ogrn", "inn", "extended"},
    "/legal-cases": {
        "ogrn", "inn", "role", "actual", "active", "date_from", "date_to",
        "claim_amount_from", "claim_amount_to", "limit", "page", "sort",
    },
    "/contracts": {"ogrn", "inn", "law", "role", "limit", "page", "sort"},
    "/inspections": {"ogrn", "inn", "limit", "page", "sort"},
    "/enforcements": {"ogrn", "inn", "limit", "page", "sort"},
    "/timeline": {"ogrn", "inn"},
    "/fedresurs": {
        "ogrn", "inn", "type", "role", "date_from", "date_to", "limit", "page", "sort",
    },
    "/bankruptcy-messages": {
        "ogrn", "inn", "date_from", "date_to", "limit", "page", "sort",
    },
    "/bank": {"bic"},
}


class TestSchemasMatchDocumentedApi:
    def test_every_tool_targets_a_documented_endpoint(self) -> None:
        assert {spec.endpoint for spec in ENDPOINT_TOOLS} <= set(API_PARAMS)
        assert HANDLER_ENDPOINTS <= set(API_PARAMS)

    def test_all_documented_endpoints_are_reachable(self) -> None:
        """Ни один метод API не должен остаться без инструмента.

        Так был потерян `/enforcements` — исполнительные производства ФССП.
        """
        reachable = {spec.endpoint for spec in ENDPOINT_TOOLS} | set(HANDLER_ENDPOINTS)
        assert reachable == set(API_PARAMS)

    def test_each_tool_is_either_wrapper_or_cascade(self) -> None:
        for spec in TOOLS:
            assert bool(spec.endpoint) != bool(spec.handler), spec.name

    @pytest.mark.parametrize("spec", ENDPOINT_TOOLS, ids=lambda s: s.name)
    def test_schema_declares_no_unknown_parameters(self, spec) -> None:
        declared = set(spec.schema["properties"]) - CLIENT_ONLY_PARAMS
        unknown = declared - API_PARAMS[spec.endpoint]
        assert not unknown, (
            f"{spec.name} объявляет параметры, которых нет у {spec.endpoint}: "
            f"{sorted(unknown)}. Агент решит, что фильтр применён, а API его проигнорирует."
        )

    @pytest.mark.parametrize("spec", TOOLS, ids=lambda s: s.name)
    def test_every_tool_offers_detail(self, spec) -> None:
        assert set(spec.schema["properties"]["detail"]["enum"]) == {"compact", "full"}

    async def test_client_only_params_never_reach_the_api(self) -> None:
        """`detail` обрабатывается сервером; попадание его в запрос — ошибка."""
        async with mcp_session() as (session, wire):
            result = await session.call_tool(
                "profile", {"identifier": "1234567890123", "detail": "full"}
            )

        assert not result.is_error
        assert CLIENT_ONLY_PARAMS.isdisjoint(wire.params)


# (инструмент, аргументы, ожидаемый путь, ожидаемые query-параметры без key)
WIRE_CASES: list[tuple[str, dict, str, dict[str, str]]] = [
    (
        "resolve",
        {"by": "founder-name", "query": "иванов иван иванович", "active": True},
        "/search",
        {"by": "founder-name", "obj": "org", "query": "иванов иван иванович", "active": "true"},
    ),
    (
        "resolve",
        {"by": "okved", "obj": "ent", "query": "62.01", "opf": "12300"},
        "/search",
        {"by": "okved", "obj": "ent", "query": "62.01", "opf": "12300"},
    ),
    # Маршрутизация по числу цифр: агенту не нужно угадывать метод.
    ("resolve", {"query": "1234567890123"}, "/company", {"ogrn": "1234567890123"}),
    ("profile", {"identifier": "1234567890123"}, "/company", {"ogrn": "1234567890123"}),
    ("profile", {"identifier": "1234567890"}, "/company", {"inn": "1234567890"}),
    ("profile", {"identifier": "01234567"}, "/company", {"okpo": "01234567"}),
    (
        "profile",
        {"identifier": "123456789012345"},
        "/entrepreneur",
        {"ogrn": "123456789012345"},
    ),
    ("profile", {"identifier": "123456789012"}, "/entrepreneur", {"inn": "123456789012"}),
    ("profile", {"identifier": "123456789"}, "/bank", {"bic": "123456789"}),
    (
        # kind принудительно выбирает метод, минуя автоопределение.
        "profile",
        {"identifier": "123456789012", "kind": "person"},
        "/person",
        {"inn": "123456789012"},
    ),
    (
        "profile",
        {"identifier": "1234567890123", "source": False},
        "/company",
        {"ogrn": "1234567890123"},
    ),
    (
        "get_finances",
        {"ogrn": "1234567890123", "extended": True},
        "/finances",
        {"ogrn": "1234567890123", "extended": "true"},
    ),
    (
        # ИНН физлица: арбитраж есть и у ИП, сужать до 10 цифр нельзя.
        "get_legal_cases",
        {"inn": "123456789012", "role": "defendant", "actual": True, "active": True},
        "/legal-cases",
        {"inn": "123456789012", "role": "defendant", "actual": "true", "active": "true"},
    ),
    (
        # ОГРНИП — 15 цифр.
        "get_legal_cases",
        {"ogrn": "123456789012345", "claim_amount_from": 100000, "sort": "-date"},
        "/legal-cases",
        {"ogrn": "123456789012345", "claim_amount_from": "100000", "sort": "-date"},
    ),
    (
        "get_contracts",
        {"inn": "1234567890", "law": "94", "role": "supplier", "sort": "-price"},
        "/contracts",
        {"inn": "1234567890", "law": "94", "role": "supplier", "sort": "-price"},
    ),
    (
        "get_inspections",
        {"ogrn": "123456789012345", "sort": "-date", "limit": 10},
        "/inspections",
        {"ogrn": "123456789012345", "sort": "-date", "limit": "10"},
    ),
    (
        "get_enforcements",
        {"inn": "1234567890", "sort": "-date"},
        "/enforcements",
        {"inn": "1234567890", "sort": "-date"},
    ),
    ("get_bank", {"bic": "123456789"}, "/bank", {"bic": "123456789"}),
    ("get_timeline", {"inn": "123456789012"}, "/timeline", {"inn": "123456789012"}),
    (
        "get_fedresurs",
        {
            "ogrn": "1234567890123",
            "type": "CreditorIntentionGoToCourt",
            "role": "publisher",
            "date_from": "2025-01-01",
        },
        "/fedresurs",
        {
            "ogrn": "1234567890123",
            "type": "CreditorIntentionGoToCourt",
            "role": "publisher",
            "date_from": "2025-01-01",
        },
    ),
    (
        "get_bankruptcy_messages",
        {"inn": "123456789012", "date_from": "2020-01-01", "date_to": "2024-12-31"},
        "/bankruptcy-messages",
        {"inn": "123456789012", "date_from": "2020-01-01", "date_to": "2024-12-31"},
    ),
]


@pytest.mark.parametrize(
    ("tool", "arguments", "path", "expected"),
    WIRE_CASES,
    ids=[f"{c[0]}:{','.join(sorted(c[1]))}" for c in WIRE_CASES],
)
async def test_outgoing_request_matches_api(
    tool: str, arguments: dict, path: str, expected: dict[str, str]
) -> None:
    async with mcp_session() as (session, wire):
        result = await session.call_tool(tool, arguments)

    assert not result.is_error, f"{tool} завершился ошибкой: {result.content}"
    assert wire.path == f"/v2{path}"

    sent = dict(wire.params)
    assert sent.pop("key") == "test-key"
    assert sent == expected


def test_wire_cases_cover_every_single_call_tool() -> None:
    """У каждого инструмента с одним запросом должен быть проверенный вызов.

    Каскады проверяются отдельно в tests/test_reports.py — там важна
    последовательность обращений, а не один запрос.
    """
    cascades = {"due_diligence_report", "bankruptcy_risk"}
    assert {case[0] for case in WIRE_CASES} == set(TOOLS_BY_NAME) - cascades
