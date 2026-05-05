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


class TestToolSpec:
    def test_is_frozen(self):
        spec = ToolSpec(name="x", endpoint="/x", description="desc" * 10, schema={"type": "object"})
        with pytest.raises(FrozenInstanceError):
            spec.name = "y"  # type: ignore[misc]
