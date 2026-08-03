"""Тесты реестра инструментов и pre-валидаторов."""

from dataclasses import FrozenInstanceError

import pytest

from checko_mcp._validation import ValidationError
from checko_mcp.tools import TOOLS, TOOLS_BY_NAME, ToolSpec

EXPECTED_TOOLS = {
    "resolve",
    "profile",
    "get_finances",
    "get_legal_cases",
    "get_contracts",
    "get_inspections",
    "get_enforcements",
    "get_bank",
    "get_timeline",
    "get_fedresurs",
    "get_bankruptcy_messages",
    "due_diligence_report",
    "bankruptcy_risk",
}


class TestRegistry:
    def test_expected_tool_names(self):
        assert {t.name for t in TOOLS} == EXPECTED_TOOLS

    def test_index_matches_tools(self):
        assert set(TOOLS_BY_NAME.keys()) == EXPECTED_TOOLS

    def test_no_duplicate_names(self):
        names = [t.name for t in TOOLS]
        assert len(names) == len(set(names))

    def test_all_have_object_schema(self):
        for tool in TOOLS:
            assert tool.schema.get("type") == "object"
            assert "properties" in tool.schema

    def test_all_have_title_and_description(self):
        for tool in TOOLS:
            assert tool.title
            assert len(tool.description) > 20

    def test_endpoints_start_with_slash(self):
        for tool in TOOLS:
            if tool.endpoint is not None:
                assert tool.endpoint.startswith("/")

    def test_descriptions_state_belarus_limitation_where_relevant(self):
        """Агент не должен считать, что по УНП можно проверить белорусскую компанию."""
        for name in ("resolve", "profile"):
            assert "УНП" in TOOLS_BY_NAME[name].description

    def test_cascades_declare_their_request_cost(self):
        """Каскад платный: агент должен видеть цену вызова в описании."""
        for name in ("due_diligence_report", "bankruptcy_risk"):
            assert "запрос" in TOOLS_BY_NAME[name].description


class TestResolveSpec:
    def test_only_query_is_required(self):
        assert TOOLS_BY_NAME["resolve"].schema["required"] == ["query"]

    def test_query_is_validated(self):
        spec = TOOLS_BY_NAME["resolve"]
        with pytest.raises(ValidationError, match="query"):
            spec.pre({})
        with pytest.raises(ValidationError, match="query"):
            spec.pre({"query": "   "})

    def test_supports_founder_and_leader_search(self):
        by = TOOLS_BY_NAME["resolve"].schema["properties"]["by"]["enum"]
        assert {"founder-name", "leader-name", "reg-date", "upd-date"} <= set(by)

    def test_supports_entrepreneur_object(self):
        assert "ent" in TOOLS_BY_NAME["resolve"].schema["properties"]["obj"]["enum"]

    def test_has_no_phantom_date_range(self):
        """У /search нет date_from/date_to — фильтр по дате идёт через by='reg-date'."""
        properties = TOOLS_BY_NAME["resolve"].schema["properties"]
        assert "date_from" not in properties
        assert "date_to" not in properties

    def test_active_is_coerced(self):
        spec = TOOLS_BY_NAME["resolve"]
        args = {"query": "тест", "active": True}
        spec.pre(args)
        assert args["active"] == "true"


class TestProfileSpec:
    def test_identifier_is_required(self):
        spec = TOOLS_BY_NAME["profile"]
        assert spec.schema["required"] == ["identifier"]
        with pytest.raises(ValidationError, match="identifier"):
            spec.pre({})

    def test_missing_identifier_points_to_resolve(self):
        with pytest.raises(ValidationError, match="resolve"):
            TOOLS_BY_NAME["profile"].pre({})

    def test_kind_covers_every_subject_type(self):
        kinds = TOOLS_BY_NAME["profile"].schema["properties"]["kind"]["enum"]
        assert set(kinds) == {"org", "entrepreneur", "person", "bank"}

    def test_source_is_coerced(self):
        spec = TOOLS_BY_NAME["profile"]
        args = {"identifier": "1234567890123", "source": "false"}
        spec.pre(args)
        assert args["source"] is None


class TestPreValidators:
    def test_person_inn_is_rejected_by_finances(self):
        """Отчётность сдают только юрлица: ИНН из 12 цифр здесь ошибка."""
        with pytest.raises(ValidationError, match="10"):
            TOOLS_BY_NAME["get_finances"].pre({"inn": "123456789012"})

    def test_legal_cases_coerces_actual_active(self):
        spec = TOOLS_BY_NAME["get_legal_cases"]
        args = {"inn": "1234567890", "actual": True, "active": False}
        spec.pre(args)
        assert args["actual"] == "true"
        assert args["active"] is None

    def test_bank_requires_bic_format(self):
        spec = TOOLS_BY_NAME["get_bank"]
        with pytest.raises(ValidationError, match="9"):
            spec.pre({"bic": "abc"})
        with pytest.raises(ValidationError, match="обязателен"):
            spec.pre({})

    def test_finances_coerces_extended(self):
        spec = TOOLS_BY_NAME["get_finances"]
        args = {"inn": "1234567890", "extended": True}
        spec.pre(args)
        assert args["extended"] == "true"

    def test_contracts_requires_law(self):
        with pytest.raises(ValidationError, match="law"):
            TOOLS_BY_NAME["get_contracts"].pre({"inn": "1234567890"})

    def test_contracts_validates_law_enum(self):
        with pytest.raises(ValidationError, match="44"):
            TOOLS_BY_NAME["get_contracts"].pre({"inn": "1234567890", "law": "99"})

    def test_contracts_accepts_int_law(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        args = {"inn": "1234567890", "law": 44}
        spec.pre(args)
        assert args["law"] == "44"

    @pytest.mark.parametrize(
        "name",
        [
            "get_inspections",
            "get_enforcements",
            "get_timeline",
            "get_fedresurs",
            "get_bankruptcy_messages",
        ],
    )
    def test_id_required_tools_reject_empty(self, name: str):
        with pytest.raises(ValidationError):
            TOOLS_BY_NAME[name].pre({})


class TestSubjectIdentifiers:
    """ИП и физлица не должны отсекаться валидатором там, где API их принимает."""

    @pytest.mark.parametrize(
        "name",
        [
            "get_legal_cases",
            "get_contracts",
            "get_inspections",
            "get_enforcements",
            "get_timeline",
            "get_fedresurs",
            "get_bankruptcy_messages",
        ],
    )
    def test_accepts_person_inn_and_ogrnip(self, name: str):
        spec = TOOLS_BY_NAME[name]
        extra = {"law": "44"} if name == "get_contracts" else {}
        spec.pre({"inn": "123456789012", **extra})
        spec.pre({"ogrn": "123456789012345", **extra})


class TestBooleanCoercion:
    def test_string_true_becomes_api_true(self):
        spec = TOOLS_BY_NAME["get_finances"]
        args = {"inn": "1234567890", "extended": "true"}
        spec.pre(args)
        assert args["extended"] == "true"

    def test_string_false_is_dropped(self):
        """Строка 'false' в запросе трактуется API как включённый флаг."""
        spec = TOOLS_BY_NAME["get_finances"]
        args = {"inn": "1234567890", "extended": "false"}
        spec.pre(args)
        assert args["extended"] is None

    def test_garbage_boolean_rejected(self):
        spec = TOOLS_BY_NAME["get_finances"]
        with pytest.raises(ValidationError, match="булевым"):
            spec.pre({"inn": "1234567890", "extended": "maybe"})


class TestContractsLaw:
    def test_accepts_94(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        args = {"inn": "1234567890", "law": "94"}
        spec.pre(args)
        assert args["law"] == "94"

    def test_schema_enum_lists_all_three_laws(self):
        law = TOOLS_BY_NAME["get_contracts"].schema["properties"]["law"]
        assert set(law["enum"]) == {"44", "94", "223"}


class TestToolSpec:
    def test_is_frozen(self):
        spec = ToolSpec(
            name="x",
            title="X",
            description="desc" * 10,
            schema={"type": "object"},
            endpoint="/x",
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "y"  # type: ignore[misc]

    def test_requires_endpoint_or_handler(self):
        with pytest.raises(ValueError, match="ровно одно"):
            ToolSpec(name="x", title="X", description="d" * 30, schema={"type": "object"})

    def test_rejects_both_endpoint_and_handler(self):
        async def handler(client, args, detail):  # pragma: no cover - не вызывается
            return {}

        with pytest.raises(ValueError, match="ровно одно"):
            ToolSpec(
                name="x",
                title="X",
                description="d" * 30,
                schema={"type": "object"},
                endpoint="/x",
                handler=handler,
            )
