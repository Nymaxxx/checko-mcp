"""Тесты сжатия ответов.

Формы данных взяты с реального API: у `/company` длинные списки лицензий,
товарных знаков и филиалов, у `/finances` — около 150 строк отчётности на каждый
год, у списочных методов — до 100 записей на страницу вместе со сводными
показателями. Именно из-за них ответы доходили до 150 000 символов.
"""

from checko_mcp._shape import NESTED_LIMIT, RECORD_LIMIT, shape

from .conftest import mcp_session


def _company(licences: int = 88, trademarks: int = 136) -> dict:
    return {
        "data": {
            "ОГРН": "1234567890123",
            "ИНН": "1234567890",
            "НаимСокр": 'ООО «Тестовая Компания»',
            "Статус": {"Код": "001", "Наим": "Действует"},
            "Руковод": [{"ФИО": "Иванов Иван Иванович", "МассРуковод": False}],
            "Лиценз": [{"Номер": str(i)} for i in range(licences)],
            "ТоварЗнак": [{"ID": i} for i in range(trademarks)],
            "Подразд": {"Филиал": [{"Наим": str(i)} for i in range(67)], "Представ": []},
            "Санкции": True,
            "НелегалФин": False,
            "НедобПост": False,
        },
        "meta": {"status": "ok", "today_request_count": 3, "balance": 0.0},
    }


def _records(count: int = 100) -> dict:
    return {
        "company": {"ОГРН": "1234567890123"},
        "data": {
            "ЗапВсего": count,
            "ОбщСуммИск": 12345678.0,
            "СтрВсего": 1,
            "СтрТекущ": 1,
            "Записи": [{"Номер": f"А40-{i}", "СуммИск": 1000.0 * i} for i in range(count)],
        },
        "meta": {"status": "ok"},
    }


class TestFullIsUntouched:
    def test_full_returns_payload_unchanged(self) -> None:
        payload = _company()
        assert shape("/company", payload, "full") is payload


class TestCompactCompany:
    def test_long_lists_are_trimmed(self) -> None:
        result = shape("/company", _company(), "compact")
        assert len(result["data"]["Лиценз"]) == NESTED_LIMIT
        assert len(result["data"]["ТоварЗнак"]) == NESTED_LIMIT
        assert len(result["data"]["Подразд"]["Филиал"]) == NESTED_LIMIT

    def test_reports_what_was_trimmed_with_real_totals(self) -> None:
        result = shape("/company", _company(), "compact")
        collapsed = result["сжатие"]["свёрнуто_всего_элементов"]
        assert collapsed["Лиценз"] == 88
        assert collapsed["ТоварЗнак"] == 136
        assert collapsed["Подразд.Филиал"] == 67

    def test_tells_agent_how_to_get_everything(self) -> None:
        result = shape("/company", _company(), "compact")
        assert any('detail="full"' in note for note in result["сжатие"]["примечания"])

    def test_risk_flags_survive_compaction(self) -> None:
        """Скалярные поля несут факторы риска — терять их нельзя."""
        result = shape("/company", _company(), "compact")
        data = result["data"]
        assert data["Санкции"] is True
        assert data["НелегалФин"] is False
        assert data["НедобПост"] is False
        assert data["Статус"] == {"Код": "001", "Наим": "Действует"}
        assert data["Руковод"][0]["ФИО"] == "Иванов Иван Иванович"

    def test_short_lists_are_left_alone(self) -> None:
        result = shape("/company", _company(licences=2, trademarks=1), "compact")
        assert len(result["data"]["Лиценз"]) == 2
        assert "Лиценз" not in result.get("сжатие", {}).get("свёрнуто_всего_элементов", {})

    def test_meta_is_never_touched(self) -> None:
        payload = _company()
        result = shape("/company", payload, "compact")
        assert result["meta"] == payload["meta"]


class TestCompactRecords:
    def test_record_list_keeps_more_than_nested_lists(self) -> None:
        result = shape("/legal-cases", _records(), "compact")
        assert len(result["data"]["Записи"]) == RECORD_LIMIT

    def test_aggregates_are_preserved(self) -> None:
        """Сводные показатели заменяют выгрузку всех записей."""
        result = shape("/legal-cases", _records(), "compact")
        assert result["data"]["ЗапВсего"] == 100
        assert result["data"]["ОбщСуммИск"] == 12345678.0

    def test_no_compaction_block_when_nothing_trimmed(self) -> None:
        result = shape("/legal-cases", _records(count=3), "compact")
        assert "сжатие" not in result


class TestCompactFinances:
    def _finances(self) -> dict:
        year = {str(code): {"СумОтч": code * 1000} for code in range(1100, 1250)}
        year["2110"] = {"СумОтч": 5_000_000}
        year["2400"] = {"СумОтч": -1_000_000}
        year["1300"] = {"СумОтч": -250_000}
        return {"data": {"2023": year, "2024": dict(year)}, "meta": {"status": "ok"}}

    def test_keeps_only_key_lines(self) -> None:
        result = shape("/finances", self._finances(), "compact")
        kept = set(result["data"]["2023"])
        assert {"2110", "2400", "1300"} <= kept
        assert len(kept) < 20

    def test_key_line_values_are_intact(self) -> None:
        result = shape("/finances", self._finances(), "compact")
        assert result["data"]["2023"]["2400"] == {"СумОтч": -1_000_000}
        assert result["data"]["2023"]["1300"] == {"СумОтч": -250_000}

    def test_all_years_are_kept(self) -> None:
        """Динамика важнее детализации: годы не режем."""
        result = shape("/finances", self._finances(), "compact")
        assert set(result["data"]) == {"2023", "2024"}


class TestQuotaWarning:
    def test_warns_when_daily_free_limit_is_close(self) -> None:
        payload = _company()
        payload["meta"]["today_request_count"] = 95
        result = shape("/company", payload, "compact")
        assert any("95" in note for note in result["сжатие"]["примечания"])

    def test_no_warning_at_normal_usage(self) -> None:
        result = shape("/company", _company(), "compact")
        notes = result["сжатие"]["примечания"]
        assert not any("бесплатных" in note for note in notes)


class TestDetailThroughProtocol:
    async def test_compact_is_the_default(self) -> None:
        async with mcp_session(payload=_company()) as (session, _wire):
            result = await session.call_tool("get_company", {"ogrn": "1234567890123"})

        assert result.is_error is False
        assert len(result.structured_content["data"]["Лиценз"]) == NESTED_LIMIT

    async def test_full_returns_everything(self) -> None:
        async with mcp_session(payload=_company()) as (session, _wire):
            result = await session.call_tool(
                "get_company", {"ogrn": "1234567890123", "detail": "full"}
            )

        assert len(result.structured_content["data"]["Лиценз"]) == 88
        assert "сжатие" not in result.structured_content

    async def test_invalid_detail_is_rejected(self) -> None:
        async with mcp_session() as (session, wire):
            result = await session.call_tool(
                "get_company", {"ogrn": "1234567890123", "detail": "подробно"}
            )

        assert result.is_error is True
        assert wire.calls == 0

    async def test_source_requires_full_detail(self) -> None:
        """source=true — это запрос полного дампа ФНС; сворачивать его бессмысленно."""
        async with mcp_session() as (session, wire):
            result = await session.call_tool(
                "get_company", {"ogrn": "1234567890123", "source": True}
            )

        assert result.is_error is True
        assert 'detail="full"' in result.content[0].text
        assert wire.calls == 0

    async def test_source_allowed_with_full(self) -> None:
        async with mcp_session() as (session, wire):
            result = await session.call_tool(
                "get_company",
                {"ogrn": "1234567890123", "source": True, "detail": "full"},
            )

        assert result.is_error is False
        assert wire.params["source"] == "true"
