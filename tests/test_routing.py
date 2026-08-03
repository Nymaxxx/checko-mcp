"""Тесты определения вида идентификатора.

Это то место, где агент ошибался чаще всего: у Checko пять идентификаторов,
и метод выбирается по числу цифр. Теперь выбор делает код, а не модель.
"""

import pytest

from checko_mcp._routing import (
    BANK,
    ENTREPRENEUR,
    ORG,
    PERSON,
    classify,
    normalize,
    route_for_kind,
    subject_params,
)
from checko_mcp._validation import ValidationError


class TestClassify:
    @pytest.mark.parametrize(
        ("identifier", "kind", "endpoint", "params"),
        [
            ("1234567890123", ORG, "/company", {"ogrn": "1234567890123"}),
            ("1234567890", ORG, "/company", {"inn": "1234567890"}),
            ("01234567", ORG, "/company", {"okpo": "01234567"}),
            ("123456789012345", ENTREPRENEUR, "/entrepreneur", {"ogrn": "123456789012345"}),
            ("123456789012", ENTREPRENEUR, "/entrepreneur", {"inn": "123456789012"}),
            ("123456789", BANK, "/bank", {"bic": "123456789"}),
        ],
    )
    def test_routes_by_digit_count(self, identifier, kind, endpoint, params) -> None:
        route = classify(identifier)
        assert (route.kind, route.endpoint, route.params) == (kind, endpoint, params)

    def test_person_inn_falls_back_from_entrepreneur_to_person(self) -> None:
        """12 цифр — ИНН физлица: сначала ЕГРИП, если ИП нет — данные физлица."""
        route = classify("123456789012")
        assert route.fallback is not None
        assert route.fallback.kind == PERSON
        assert route.fallback.endpoint == "/person"

    def test_person_route_warns_about_personal_data(self) -> None:
        route = classify("123456789012")
        assert "152-ФЗ" in (route.note or "")

    def test_okpo_falls_back_to_entrepreneur(self) -> None:
        route = classify("01234567")
        assert route.fallback is not None
        assert route.fallback.endpoint == "/entrepreneur"

    def test_nine_digits_mentions_belarusian_unp(self) -> None:
        """У БИК и белорусского УНП одинаковая длина — агента надо предупредить."""
        assert "УНП" in (classify("123456789").note or "")

    @pytest.mark.parametrize("bad", ["", "   ", "ООО Ромашка", "12АБ34"])
    def test_rejects_non_digits(self, bad) -> None:
        with pytest.raises(ValidationError):
            classify(bad)

    def test_non_digits_hint_points_to_resolve(self) -> None:
        with pytest.raises(ValidationError, match="resolve"):
            classify("Ромашка")

    @pytest.mark.parametrize("bad", ["1", "1234567", "12345678901", "1234567890123456"])
    def test_rejects_unknown_lengths(self, bad) -> None:
        with pytest.raises(ValidationError, match="Не удалось определить"):
            classify(bad)


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (" 1234567890123 ", "1234567890123"),
            ("1234 5678 9012 3", "1234567890123"),
            ("310-402-910-200-035", "310402910200035"),
            (None, ""),
        ],
    )
    def test_strips_separators(self, raw, expected) -> None:
        assert normalize(raw) == expected


class TestRouteForKind:
    def test_forces_person_over_entrepreneur(self) -> None:
        route = route_for_kind("123456789012", PERSON)
        assert (route.endpoint, route.fallback) == ("/person", None)

    def test_entrepreneur_accepts_ogrnip_inn_and_okpo(self) -> None:
        assert route_for_kind("123456789012345", ENTREPRENEUR).params == {
            "ogrn": "123456789012345"
        }
        assert route_for_kind("123456789012", ENTREPRENEUR).params == {"inn": "123456789012"}
        assert route_for_kind("01234567", ENTREPRENEUR).params == {"okpo": "01234567"}

    def test_rejects_length_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="12 цифр"):
            route_for_kind("1234567890", PERSON)
        with pytest.raises(ValidationError, match="9 цифр"):
            route_for_kind("1234567890", BANK)

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError, match="Неизвестный вид"):
            route_for_kind("1234567890", "юрлицо")


class TestSubjectParams:
    @pytest.mark.parametrize(
        ("identifier", "expected"),
        [
            ("1234567890123", {"ogrn": "1234567890123"}),
            ("123456789012345", {"ogrn": "123456789012345"}),
            ("1234567890", {"inn": "1234567890"}),
            ("123456789012", {"inn": "123456789012"}),
        ],
    )
    def test_picks_right_parameter_name(self, identifier, expected) -> None:
        assert subject_params(identifier) == expected

    def test_rejects_okpo_and_bic(self) -> None:
        """У методов с фильтрами нет ни ОКПО, ни БИК."""
        with pytest.raises(ValidationError):
            subject_params("01234567")
        with pytest.raises(ValidationError):
            subject_params("123456789")
