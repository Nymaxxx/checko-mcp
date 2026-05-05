"""Тесты для модуля валидации."""

import pytest

from checko_mcp._validation import (
    ValidationError,
    check_format,
    coerce_bool,
    require_any,
)


class TestRequireAny:
    def test_passes_when_any_key_present(self):
        require_any({"ogrn": "123"}, "ogrn", "inn")

    def test_passes_when_all_keys_present(self):
        require_any({"ogrn": "123", "inn": "456"}, "ogrn", "inn")

    def test_raises_when_all_missing(self):
        with pytest.raises(ValidationError, match="ogrn"):
            require_any({}, "ogrn", "inn")

    def test_raises_on_falsy_values(self):
        with pytest.raises(ValidationError):
            require_any({"ogrn": "", "inn": None}, "ogrn", "inn")


class TestCheckFormat:
    def test_none_skipped(self):
        check_format(None, "inn", 10)

    def test_correct_digits(self):
        check_format("1234567890", "inn", 10)

    def test_wrong_length(self):
        with pytest.raises(ValidationError, match="10 цифр"):
            check_format("123", "inn", 10)

    def test_non_digit(self):
        with pytest.raises(ValidationError, match="10 цифр"):
            check_format("12345abcde", "inn", 10)

    def test_strips_whitespace(self):
        check_format("  1234567890  ", "inn", 10)


class TestCoerceBool:
    def test_true_to_string(self):
        args = {"source": True}
        coerce_bool(args, "source")
        assert args["source"] == "true"

    def test_false_to_none(self):
        args = {"source": False}
        coerce_bool(args, "source")
        assert args["source"] is None

    def test_strings_unchanged(self):
        args = {"source": "true"}
        coerce_bool(args, "source")
        assert args["source"] == "true"

    def test_missing_key_ignored(self):
        args: dict = {}
        coerce_bool(args, "source")
        assert args == {}

    def test_multiple_keys(self):
        args = {"actual": True, "active": False, "extra": "x"}
        coerce_bool(args, "actual", "active")
        assert args == {"actual": "true", "active": None, "extra": "x"}
