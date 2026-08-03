"""Тесты каскадных инструментов.

Каскад ценен ровно тем, что делает несколько запросов сам и считает сигналы
детерминированно. Поэтому проверяется и состав обращений к API, и правила,
по которым сигналы возникают.
"""

import httpx2 as httpx
import pytest

from checko_mcp._reports import CRITICAL, IMPORTANT

from .conftest import mcp_session

COMPANY_CARD = {
    "ОГРН": "1234567890123",
    "ИНН": "1234567890",
    "НаимСокр": 'ООО «Тестовая Компания»',
    "Статус": {"Код": "001", "Наим": "Действует"},
    "Руковод": [{"ФИО": "Иванов Иван Иванович"}],
    "Санкции": False,
    "НелегалФин": False,
    "НедобПост": False,
    "ЕФРСБ": [],
}


def _router(overrides: dict[str, dict] | None = None):
    """Отвечает разными данными в зависимости от запрошенного метода."""
    overrides = overrides or {}
    defaults: dict[str, dict] = {
        "/company": {"data": dict(COMPANY_CARD)},
        "/entrepreneur": {"data": {}},
        "/person": {"data": {}},
        "/search": {"data": {"ЗапВсего": 0, "Записи": []}},
        "/finances": {"data": {}},
        "/legal-cases": {"data": {"ЗапВсего": 0, "ОбщСуммИск": 0, "Записи": []}},
        "/enforcements": {"data": {"ОбщКолич": 0, "ОбщСум": 0, "ОстЗадолж": 0, "ЗапВсего": 0}},
        "/fedresurs": {"data": {"ЗапВсего": 0, "Записи": []}},
        "/bankruptcy-messages": {"data": {"ЗапВсего": 0, "Записи": []}},
        "/bank": {"data": {}},
    }
    defaults.update(overrides)

    def handler(request: httpx.Request) -> dict:
        path = request.url.path.replace("/v2", "", 1)
        payload = dict(defaults.get(path, {"data": {}}))
        payload["meta"] = {"status": "ok", "today_request_count": 1, "balance": 0.0}
        return payload

    return handler


class TestDueDiligenceReport:
    async def test_queries_all_six_registries_in_one_call(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        assert result.is_error is False
        assert set(p.replace("/v2", "", 1) for p in wire.paths) == {
            "/company",
            "/finances",
            "/legal-cases",
            "/enforcements",
            "/fedresurs",
            "/bankruptcy-messages",
        }

    async def test_reports_how_many_requests_it_spent(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )
        assert result.structured_content["запросов_в_api"] == wire.calls == 6

    async def test_skips_finances_for_entrepreneur(self) -> None:
        """Отчётность сдают только юрлица — лишний платный запрос не нужен."""
        overrides = {"/entrepreneur": {"data": {"ОГРНИП": "123456789012345", "ФИО": "И."}}}
        async with mcp_session(payload=_router(overrides)) as (session, wire):
            await session.call_tool("due_diligence_report", {"identifier": "123456789012345"})

        assert "/v2/finances" not in wire.paths
        assert wire.calls == 5

    async def test_asks_for_defendant_role_and_active_cases(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            await session.call_tool("due_diligence_report", {"identifier": "1234567890123"})

        cases = next(params for path, params in wire.requests if path.endswith("/legal-cases"))
        assert cases["role"] == "defendant"
        assert cases["actual"] == "true"
        assert cases["active"] == "true"

    async def test_no_signals_when_everything_is_clean(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )
        report = result.structured_content
        assert report["сигналов_не_найдено"] is True
        assert report["сигналы"] == []

    async def test_bankruptcy_intention_is_critical(self) -> None:
        overrides = {
            "/fedresurs": {
                "data": {
                    "ЗапВсего": 1,
                    "Записи": [{"Тип": "CreditorIntentionGoToCourt", "Дата": "2026-01-01"}],
                }
            }
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        signals = result.structured_content["сигналы"]
        assert signals[0]["уровень"] == CRITICAL
        assert "намерении" in signals[0]["факт"] or "намерен" in signals[0]["факт"]

    async def test_liquidated_status_is_critical(self) -> None:
        card = dict(COMPANY_CARD, Статус={"Код": "701", "Наим": "Ликвидирована"})
        async with mcp_session(payload=_router({"/company": {"data": card}})) as (session, _w):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        signals = result.structured_content["сигналы"]
        assert any(s["уровень"] == CRITICAL and "Ликвидирована" in s["факт"] for s in signals)

    async def test_enforcement_balance_becomes_a_signal(self) -> None:
        overrides = {
            "/enforcements": {
                "data": {"ОбщКолич": 115, "ОбщСум": 3906823.39, "ОстЗадолж": 2311749.75}
            }
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        report = result.structured_content
        assert report["исполнительные_производства"]["ОбщКолич"] == 115
        assert any(s["источник"] == "ФССП" for s in report["сигналы"])

    async def test_negative_capital_becomes_a_signal(self) -> None:
        overrides = {"/finances": {"data": {"2024": {"1300": {"СумОтч": -5_000_000}}}}}
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        signals = result.structured_content["сигналы"]
        assert any(s["источник"] == "строка 1300" and s["уровень"] == IMPORTANT for s in signals)

    async def test_signals_are_ordered_by_severity(self) -> None:
        card = dict(COMPANY_CARD, Санкции=True, МассУчред=True)
        overrides = {
            "/company": {"data": card},
            "/enforcements": {"data": {"ОбщКолич": 2, "ОбщСум": 100.0, "ОстЗадолж": 100.0}},
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        levels = [s["уровень"] for s in result.structured_content["сигналы"]]
        assert levels == sorted(levels, key=lambda level: {CRITICAL: 0, IMPORTANT: 1}.get(level, 2))

    async def test_source_failure_does_not_break_the_report(self) -> None:
        """Сбой одного реестра не должен обнулять остальную проверку."""

        def handler(request: httpx.Request) -> dict:
            path = request.url.path.replace("/v2", "", 1)
            if path == "/enforcements":
                return {"data": {}, "meta": {"status": "error", "message": "недоступно"}}
            return _router()(request)

        async with mcp_session(payload=handler) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )

        report = result.structured_content
        assert result.is_error is False
        assert any("исполнительные" in item for item in report["не_удалось_проверить"])
        assert "активные_иски_как_ответчик" in report

    async def test_does_not_invent_a_verdict(self) -> None:
        """Отчёт приводит факты и сигналы, но вывод о сделке оставляет агенту."""
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report", {"identifier": "1234567890123"}
            )
        report = result.structured_content
        assert "оговорка" in report
        assert not {"вывод", "вердикт", "рекомендация"} & set(report)

    async def test_purpose_is_carried_into_report(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool(
                "due_diligence_report",
                {"identifier": "1234567890123", "purpose": "поставка оборудования"},
            )
        assert result.structured_content["цель_проверки"] == "поставка оборудования"

    async def test_ambiguous_name_asks_to_clarify(self) -> None:
        overrides = {
            "/search": {
                "data": {
                    "ЗапВсего": 2,
                    "Записи": [
                        {"ОГРН": "1" * 13, "ИНН": "1" * 10, "НаимСокр": "ООО «Ромашка»"},
                        {"ОГРН": "2" * 13, "ИНН": "2" * 10, "НаимСокр": "АО «Ромашка»"},
                    ],
                }
            }
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool("due_diligence_report", {"identifier": "Ромашка"})

        assert result.is_error is True
        assert "уточните" in result.content[0].text.lower()

    async def test_bank_bic_is_rejected_with_a_hint(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool("due_diligence_report", {"identifier": "123456789"})

        assert result.is_error is True
        assert "get_bank" in result.content[0].text


class TestBankruptcyRisk:
    async def test_checks_four_independent_sources(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            result = await session.call_tool("bankruptcy_risk", {"identifier": "1234567890123"})

        paths = {p.replace("/v2", "", 1) for p in wire.paths}
        assert {"/bankruptcy-messages", "/fedresurs", "/enforcements", "/finances"} <= paths
        assert len(result.structured_content["проверенные_источники"]) == 4

    async def test_filters_fedresurs_by_intention_type(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            await session.call_tool("bankruptcy_risk", {"identifier": "1234567890123"})

        params = next(p for path, p in wire.requests if path.endswith("/fedresurs"))
        assert params["type"] == "CreditorIntentionGoToCourt"

    async def test_efrsb_records_are_critical(self) -> None:
        overrides = {"/bankruptcy-messages": {"data": {"ЗапВсего": 3, "Записи": []}}}
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool("bankruptcy_risk", {"identifier": "1234567890123"})

        signals = result.structured_content["сигналы"]
        assert any(s["уровень"] == CRITICAL and s["источник"] == "ЕФРСБ" for s in signals)

    async def test_reports_no_signals_for_clean_subject(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool("bankruptcy_risk", {"identifier": "1234567890123"})
        assert result.structured_content["сигналов_не_найдено"] is True

    async def test_does_not_compute_a_probability(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool("bankruptcy_risk", {"identifier": "1234567890123"})
        assert not {"вероятность", "оценка_риска", "балл"} & set(result.structured_content)


class TestResolve:
    async def test_projects_candidates_to_identity_fields(self) -> None:
        """Смысл resolve — короткий список, а не 100 полных записей."""
        overrides = {
            "/search": {
                "data": {
                    "ЗапВсего": 100,
                    "Записи": [
                        {
                            "ОГРН": str(i) * 13,
                            "ИНН": str(i) * 10,
                            "НаимСокр": f"ООО «Тест {i}»",
                            "ЮрАдрес": "...",
                            "Руковод": [{"ФИО": "..."}],
                            "Учред": {"ФЛ": [{"ФИО": "..."}]},
                        }
                        for i in range(1, 10)
                    ],
                }
            }
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool("resolve", {"query": "тест"})

        payload = result.structured_content
        assert payload["найдено_всего"] == 100
        assert "Руковод" not in payload["кандидаты"][0]
        assert payload["кандидаты"][0]["НаимСокр"] == "ООО «Тест 1»"

    async def test_limit_caps_candidates(self) -> None:
        overrides = {
            "/search": {
                "data": {
                    "ЗапВсего": 50,
                    "Записи": [{"ОГРН": str(i) * 13} for i in range(50)],
                }
            }
        }
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool("resolve", {"query": "тест", "limit": 3})

        assert result.structured_content["показано"] == 3
        assert "примечание" in result.structured_content

    async def test_full_detail_returns_raw_search(self) -> None:
        overrides = {"/search": {"data": {"ЗапВсего": 1, "Записи": [{"ОГРН": "1" * 13}]}}}
        async with mcp_session(payload=_router(overrides)) as (session, _wire):
            result = await session.call_tool(
                "resolve", {"query": "тест", "detail": "full"}
            )
        assert "Записи" in result.structured_content["data"]

    async def test_identifier_skips_search_entirely(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            result = await session.call_tool("resolve", {"query": "1234567890123"})

        assert "/v2/search" not in wire.paths
        assert result.structured_content["распознано_как"] == "org"


class TestProfile:
    async def test_falls_back_to_person_when_no_entrepreneur(self) -> None:
        overrides = {
            "/entrepreneur": {"data": {}},
            "/person": {"data": {"ИНН": "123456789012", "ФИО": "И. И. И."}},
        }
        async with mcp_session(payload=_router(overrides)) as (session, wire):
            result = await session.call_tool("profile", {"identifier": "123456789012"})

        assert [p.replace("/v2", "", 1) for p in wire.paths] == ["/entrepreneur", "/person"]
        assert result.structured_content["субъект"]["вид"] == "person"

    async def test_keeps_entrepreneur_when_found(self) -> None:
        overrides = {"/entrepreneur": {"data": {"ОГРНИП": "123456789012345"}}}
        async with mcp_session(payload=_router(overrides)) as (session, wire):
            result = await session.call_tool("profile", {"identifier": "123456789012"})

        assert wire.calls == 1
        assert result.structured_content["субъект"]["вид"] == "entrepreneur"

    async def test_warns_about_personal_data_for_person_inn(self) -> None:
        async with mcp_session(payload=_router()) as (session, _wire):
            result = await session.call_tool("profile", {"identifier": "123456789012"})

        notes = result.structured_content["субъект"]["примечания"]
        assert any("152-ФЗ" in note for note in notes)

    async def test_empty_answer_is_flagged_not_silently_returned(self) -> None:
        """На белорусский УНП API отвечает 200 с пустым data — это надо назвать."""
        async with mcp_session(payload=_router({"/bank": {"data": {}}})) as (session, _wire):
            result = await session.call_tool("profile", {"identifier": "123456789"})

        notes = result.structured_content["субъект"]["примечания"]
        assert any("УНП" in note for note in notes)

    async def test_rejects_text_with_a_pointer_to_resolve(self) -> None:
        async with mcp_session(payload=_router()) as (session, wire):
            result = await session.call_tool("profile", {"identifier": "ООО Ромашка"})

        assert result.is_error is True
        assert "resolve" in result.content[0].text
        assert wire.calls == 0


@pytest.mark.parametrize("tool", ["due_diligence_report", "bankruptcy_risk", "profile"])
async def test_identifier_is_required(tool: str) -> None:
    async with mcp_session(payload=_router()) as (session, wire):
        result = await session.call_tool(tool, {})

    assert result.is_error is True
    assert wire.calls == 0
