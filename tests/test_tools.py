"""Тесты реестра инструментов и pre-валидаторов."""

from dataclasses import FrozenInstanceError

import pytest

from checko_mcp._validation import ValidationError
from checko_mcp.tools import TOOLS, TOOLS_BY_NAME, ToolSpec

EXPECTED_TOOLS = {
    "search",
    "get_company",
    "get_entrepreneur",
    "get_person",
    "get_finances",
    "get_legal_cases",
    "get_contracts",
    "get_inspections",
    "get_enforcements",
    "get_bank",
    "get_timeline",
    "get_fedresurs",
    "get_bankruptcy_messages",
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

    def test_all_have_endpoint_and_description(self):
        for tool in TOOLS:
            assert tool.endpoint.startswith("/")
            assert len(tool.description) > 20
            assert tool.title

    def test_descriptions_state_belarus_limitation_where_relevant(self):
        """Агент не должен считать, что по УНП можно проверить белорусскую компанию."""
        for name in ("search", "get_company", "get_entrepreneur"):
            assert "УНП" in TOOLS_BY_NAME[name].description


class TestPreValidators:
    def test_company_requires_id(self):
        spec = TOOLS_BY_NAME["get_company"]
        with pytest.raises(ValidationError):
            spec.pre({})

    def test_company_validates_ogrn_length(self):
        spec = TOOLS_BY_NAME["get_company"]
        with pytest.raises(ValidationError, match="13"):
            spec.pre({"ogrn": "123"})

    def test_company_coerces_source_bool(self):
        spec = TOOLS_BY_NAME["get_company"]
        args = {"inn": "1234567890", "source": True}
        spec.pre(args)
        assert args["source"] == "true"

    def test_entrepreneur_accepts_okpo(self):
        spec = TOOLS_BY_NAME["get_entrepreneur"]
        spec.pre({"okpo": "12345678"})

    def test_person_requires_inn_format(self):
        spec = TOOLS_BY_NAME["get_person"]
        with pytest.raises(ValidationError, match="12"):
            spec.pre({"inn": "123"})

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

    def test_finances_coerces_extended(self):
        spec = TOOLS_BY_NAME["get_finances"]
        args = {"inn": "1234567890", "extended": True}
        spec.pre(args)
        assert args["extended"] == "true"

    def test_search_requires_by_obj_query(self):
        spec = TOOLS_BY_NAME["search"]
        with pytest.raises(ValidationError, match="query"):
            spec.pre({"by": "name", "obj": "org"})
        with pytest.raises(ValidationError, match="by"):
            spec.pre({"obj": "org", "query": "x"})
        with pytest.raises(ValidationError, match="obj"):
            spec.pre({"by": "name", "query": "x"})

    def test_search_passes_minimal(self):
        spec = TOOLS_BY_NAME["search"]
        spec.pre({"by": "name", "obj": "org", "query": "ООО Тест"})

    def test_search_schema_lists_required_in_order(self):
        spec = TOOLS_BY_NAME["search"]
        assert spec.schema["required"] == ["by", "obj", "query"]

    def test_contracts_requires_law(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        with pytest.raises(ValidationError, match="law"):
            spec.pre({"inn": "1234567890"})

    def test_contracts_validates_law_enum(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        with pytest.raises(ValidationError, match="44"):
            spec.pre({"inn": "1234567890", "law": "99"})

    def test_contracts_accepts_int_law(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        args = {"inn": "1234567890", "law": 44}
        spec.pre(args)
        assert args["law"] == "44"

    def test_contracts_passes_minimal(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        spec.pre({"inn": "1234567890", "law": "223"})

    @pytest.mark.parametrize(
        "name",
        ["get_inspections", "get_timeline", "get_fedresurs", "get_bankruptcy_messages"],
    )
    def test_id_required_tools_reject_empty(self, name: str):
        spec = TOOLS_BY_NAME[name]
        with pytest.raises(ValidationError):
            spec.pre({})


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

    @pytest.mark.parametrize("name", ["get_company", "get_finances"])
    def test_org_only_tools_still_reject_person_inn(self, name: str):
        """У юрлица ИНН всегда 10 цифр — 12 здесь действительно ошибка."""
        spec = TOOLS_BY_NAME[name]
        with pytest.raises(ValidationError, match="10"):
            spec.pre({"inn": "123456789012"})

    def test_entrepreneur_maps_ogrnip_alias_to_ogrn(self):
        """У метода /entrepreneur параметр называется ogrn, а не ogrnip."""
        spec = TOOLS_BY_NAME["get_entrepreneur"]
        args = {"ogrnip": "123456789012345"}
        spec.pre(args)
        assert args == {"ogrn": "123456789012345"}

    def test_entrepreneur_rejects_org_ogrn_length(self):
        spec = TOOLS_BY_NAME["get_entrepreneur"]
        with pytest.raises(ValidationError, match="15"):
            spec.pre({"ogrn": "1234567890123"})


class TestBooleanCoercion:
    def test_string_true_becomes_api_true(self):
        spec = TOOLS_BY_NAME["get_company"]
        args = {"inn": "1234567890", "source": "true"}
        spec.pre(args)
        assert args["source"] == "true"

    def test_string_false_is_dropped(self):
        """Строка 'false' в запросе трактуется API как включённый флаг."""
        spec = TOOLS_BY_NAME["get_company"]
        args = {"inn": "1234567890", "source": "false"}
        spec.pre(args)
        assert args["source"] is None

    def test_garbage_boolean_rejected(self):
        spec = TOOLS_BY_NAME["get_company"]
        with pytest.raises(ValidationError, match="булевым"):
            spec.pre({"inn": "1234567890", "source": "maybe"})


class TestContractsLaw:
    def test_accepts_94(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        args = {"inn": "1234567890", "law": "94"}
        spec.pre(args)
        assert args["law"] == "94"

    def test_schema_enum_lists_all_three_laws(self):
        spec = TOOLS_BY_NAME["get_contracts"]
        assert set(spec.schema["properties"]["law"]["enum"]) == {"44", "94", "223"}


class TestSearchCapabilities:
    def test_supports_founder_and_leader_search(self):
        spec = TOOLS_BY_NAME["search"]
        assert {"founder-name", "leader-name", "reg-date", "upd-date"} <= set(
            spec.schema["properties"]["by"]["enum"]
        )

    def test_supports_entrepreneur_object(self):
        spec = TOOLS_BY_NAME["search"]
        assert "ent" in spec.schema["properties"]["obj"]["enum"]

    def test_has_no_phantom_date_range(self):
        """У /search нет date_from/date_to — фильтр по дате идёт через by='reg-date'."""
        properties = TOOLS_BY_NAME["search"].schema["properties"]
        assert "date_from" not in properties
        assert "date_to" not in properties


class TestToolSpec:
    def test_is_frozen(self):
        spec = ToolSpec(
            name="x",
            endpoint="/x",
            title="X",
            description="desc" * 10,
            schema={"type": "object"},
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "y"  # type: ignore[misc]
