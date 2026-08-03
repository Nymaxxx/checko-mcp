"""Тесты MCP-prompts.

Используются только синтетические идентификаторы (структурно валидные, но не существующие в реестрах).
"""

import pytest

from checko_mcp._validation import ValidationError
from checko_mcp.prompts import (
    PROMPTS,
    PROMPTS_BY_NAME,
    get_prompt,
    list_prompts,
)

EXPECTED_PROMPTS = {
    "check_counterparty",
    "verify_bank_details",
    "assess_bankruptcy_risk",
    "audit_person",
    "evaluate_tender_participant",
    "analyze_finances",
}

SYNTH_INN_LEGAL = "1234567890"          # 10 цифр — для юрлица
SYNTH_INN_PERSON = "123456789012"       # 12 цифр — для физлица/ИП
SYNTH_OGRN = "1234567890123"            # 13 цифр
SYNTH_BIC = "123456789"                 # 9 цифр


class TestRegistry:
    def test_expected_prompts(self):
        assert {p.name for p in PROMPTS} == EXPECTED_PROMPTS

    def test_no_duplicate_names(self):
        names = [p.name for p in PROMPTS]
        assert len(names) == len(set(names))

    def test_index_matches(self):
        assert set(PROMPTS_BY_NAME.keys()) == EXPECTED_PROMPTS


class TestListPrompts:
    def test_returns_all(self):
        result = list_prompts()
        assert {p.name for p in result} == EXPECTED_PROMPTS

    def test_each_has_args_metadata(self):
        for p in list_prompts():
            assert p.title
            assert p.description
            for arg in p.arguments or []:
                assert arg.name
                assert arg.description


class TestCheckCounterparty:
    def test_minimal(self):
        result = get_prompt("check_counterparty", {"query": "Тестовая Компания"})
        assert len(result.messages) == 1
        text = result.messages[0].content.text
        assert "Тестовая Компания" in text
        assert "due_diligence_report" in text
        assert "сигналы" in text
        assert "Цель:" not in text

    def test_with_purpose(self):
        result = get_prompt(
            "check_counterparty",
            {"query": "ООО Тест", "purpose": "договор поставки на 5 млн"},
        )
        text = result.messages[0].content.text
        assert "Цель: договор поставки на 5 млн" in text

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError, match="query"):
            get_prompt("check_counterparty", {})


class TestVerifyBankDetails:
    def test_juridical_inn(self):
        result = get_prompt(
            "verify_bank_details", {"inn": SYNTH_INN_LEGAL, "bic": SYNTH_BIC}
        )
        text = result.messages[0].content.text
        assert 'kind="org"' in text
        assert "get_bank" in text
        assert SYNTH_BIC in text

    def test_individual_inn(self):
        result = get_prompt(
            "verify_bank_details", {"inn": SYNTH_INN_PERSON, "bic": SYNTH_BIC}
        )
        text = result.messages[0].content.text
        assert 'kind="entrepreneur"' in text

    def test_invalid_inn_length(self):
        with pytest.raises(ValidationError):
            get_prompt("verify_bank_details", {"inn": "123", "bic": SYNTH_BIC})

    def test_invalid_bic(self):
        with pytest.raises(ValidationError, match="bic"):
            get_prompt("verify_bank_details", {"inn": SYNTH_INN_LEGAL, "bic": "12"})

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            get_prompt("verify_bank_details", {"inn": SYNTH_INN_LEGAL})


class TestAssessBankruptcyRisk:
    def test_juridical(self):
        result = get_prompt("assess_bankruptcy_risk", {"inn": SYNTH_INN_LEGAL})
        text = result.messages[0].content.text
        assert "bankruptcy_risk" in text
        assert "CreditorIntentionGoToCourt" in text
        assert "ЕФРСБ" in text

    def test_individual_with_context(self):
        result = get_prompt(
            "assess_bankruptcy_risk",
            {"inn": SYNTH_INN_PERSON, "context": "не платит 4 месяца"},
        )
        text = result.messages[0].content.text
        assert "bankruptcy_risk" in text
        assert "Контекст: не платит 4 месяца" in text

    def test_invalid_inn_length(self):
        with pytest.raises(ValidationError):
            get_prompt("assess_bankruptcy_risk", {"inn": "abc"})


class TestAuditPerson:
    def test_valid_inn(self):
        result = get_prompt("audit_person", {"inn": SYNTH_INN_PERSON})
        text = result.messages[0].content.text
        assert 'kind="person"' in text
        assert "152-ФЗ" in text
        assert "checko://playbooks/audit/methodology" in text

    def test_invalid_inn_length(self):
        with pytest.raises(ValidationError, match="12"):
            get_prompt("audit_person", {"inn": SYNTH_INN_LEGAL})


class TestEvaluateTenderParticipant:
    def test_minimal(self):
        result = get_prompt(
            "evaluate_tender_participant", {"query": "ООО Тестовый Поставщик"}
        )
        text = result.messages[0].content.text
        assert "get_contracts" in text
        assert "get_inspections" in text
        assert "НедобПост" in text


class TestAnalyzeFinances:
    def test_with_ogrn(self):
        result = get_prompt(
            "analyze_finances", {"ogrn_or_inn": SYNTH_OGRN}
        )
        text = result.messages[0].content.text
        assert f'ogrn="{SYNTH_OGRN}"' in text
        assert "extended=true" in text
        assert "5 лет" in text

    def test_with_inn_and_years(self):
        result = get_prompt(
            "analyze_finances", {"ogrn_or_inn": SYNTH_INN_LEGAL, "years": "3"}
        )
        text = result.messages[0].content.text
        assert f'inn="{SYNTH_INN_LEGAL}"' in text
        assert "3 лет" in text

    def test_invalid_identifier(self):
        with pytest.raises(ValidationError, match="ОГРН"):
            get_prompt("analyze_finances", {"ogrn_or_inn": "abc"})


class TestUnknownPrompt:
    def test_raises(self):
        with pytest.raises(ValidationError, match="Неизвестный"):
            get_prompt("does_not_exist", {})
