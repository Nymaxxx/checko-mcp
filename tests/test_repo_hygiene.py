"""Проверка правила «в репозитории только синтетические идентификаторы».

Правило записано в `AGENTS.md`, но до этого теста существовало только как текст,
и в README успел попасть настоящий ИНН крупного банка. Настоящий ИНН, ОГРН или
БИК в примере — это не опечатка: агент, читающий документацию как инструкцию,
начинает обращаться к API по реальному субъекту, а в случае ИНН-12 запрашивать
персональные данные конкретного человека без законного основания (152-ФЗ).
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Идентификаторы в коде и документации всегда закавычены, а денежные суммы
# в примерах ответов API идут числами (`"ОбщСум": 987654321.0`), поэтому
# кавычки отделяют одно от другого без белого списка полей.
_QUOTED_DIGITS = re.compile(r"[\"«`'](\d{8,15})[\"»`']")

# Каталоги сборки, кэшей и окружений: их содержимое не является частью репозитория.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
        "node_modules",
        ".idea",
        ".vscode",
        "reports",
    }
)

# Канонический набор из AGENTS.md. Добавлять сюда новое значение можно только
# если оно заведомо не принадлежит ни одному реальному субъекту.
ALLOWED = frozenset(
    {
        "01234567",  # ОКПО, 8 цифр
        "123456789",  # БИК и КПП, 9 цифр
        "1234567890",  # ИНН юрлица, 10 цифр
        "9999999999",  # второй ИНН-10: нужен, чтобы различать субъектов в тестах кэша
        "12345678901",  # 11 цифр — заведомо невалидная длина, проверка отказа
        "123456789012",  # ИНН физлица или ИП, 12 цифр
        "1234567890123",  # ОГРН, 13 цифр
        "123456789012345",  # ОГРНИП, 15 цифр
    }
)


SELF = Path(__file__).resolve()


def _tracked_text_files(*, include_self: bool = True) -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if not include_self and path.resolve() == SELF:
            continue
        files.append(path)
    return files


def _quoted_digit_runs(text: str) -> set[str]:
    return set(_QUOTED_DIGITS.findall(text))


class TestSyntheticIdentifiersOnly:
    def test_no_real_identifiers_anywhere(self) -> None:
        offenders: dict[str, list[str]] = {}

        for path in _tracked_text_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for value in _quoted_digit_runs(text) - ALLOWED:
                rel = str(path.relative_to(REPO_ROOT))
                offenders.setdefault(value, []).append(rel)

        assert not offenders, (
            "Найдены идентификаторы вне канонического синтетического набора. "
            "Замените их значениями из AGENTS.md либо, если значение заведомо "
            f"ничему не принадлежит, добавьте его в ALLOWED: {offenders}"
        )

    @pytest.mark.parametrize("value", sorted(ALLOWED))
    def test_allowed_set_is_actually_used(self, value: str) -> None:
        """Мёртвое разрешение — это дырка: набор должен сужаться, а не копиться.

        Этот файл из обхода исключён: иначе перечисление в `ALLOWED` само
        считалось бы использованием, и проверка не значила бы ничего.
        """
        used = any(
            value in _quoted_digit_runs(path.read_text(encoding="utf-8", errors="ignore"))
            for path in _tracked_text_files(include_self=False)
        )
        assert used, f"{value} больше нигде не используется — удалите его из ALLOWED"
