"""Тесты MCP-resources."""

import pytest

from checko_mcp.resources import (
    RESOURCES,
    RESOURCES_BY_URI,
    list_resources,
    read_resource_text,
)

EXPECTED_URIS = {
    "checko://docs/agent-guide",
    "checko://docs/legal",
    "checko://playbooks/audit/methodology",
    "checko://playbooks/audit/anomaly-checklist",
    "checko://playbooks/audit/template",
}


class TestRegistry:
    def test_expected_uris(self):
        assert {r.uri for r in RESOURCES} == EXPECTED_URIS

    def test_uniqueness(self):
        names = [r.name for r in RESOURCES]
        assert len(names) == len(set(names))

    def test_index_matches(self):
        assert set(RESOURCES_BY_URI.keys()) == EXPECTED_URIS


class TestListResources:
    def test_returns_mcp_resources(self):
        result = list_resources()
        assert len(result) == len(EXPECTED_URIS)
        for r in result:
            assert r.mimeType == "text/markdown"
            assert r.name
            assert r.title
            assert r.description


class TestReadResource:
    @pytest.mark.parametrize("uri", sorted(EXPECTED_URIS))
    def test_each_resource_loads(self, uri: str):
        text = read_resource_text(uri)
        assert isinstance(text, str)
        assert len(text) > 100

    def test_unknown_uri_raises(self):
        with pytest.raises(FileNotFoundError, match="Неизвестный"):
            read_resource_text("checko://does/not/exist")

    def test_agent_guide_mentions_prompts_section(self):
        text = read_resource_text("checko://docs/agent-guide")
        assert "check_counterparty" in text
        assert "verify_bank_details" in text

    def test_legal_mentions_152_fz(self):
        text = read_resource_text("checko://docs/legal")
        assert "152-ФЗ" in text or "152" in text

    def test_methodology_has_audit_steps(self):
        text = read_resource_text("checko://playbooks/audit/methodology")
        assert "Этап" in text
