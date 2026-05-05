"""Валидаторы и хелперы для аргументов MCP-инструментов."""

from typing import Any


class ValidationError(Exception):
    """Ошибка валидации аргументов инструмента."""


def require_any(args: dict[str, Any], *keys: str) -> None:
    """Хотя бы один из ключей должен присутствовать и быть истинным."""
    if not any(args.get(k) for k in keys):
        names = " или ".join(f"'{k}'" for k in keys)
        raise ValidationError(f"Необходимо указать {names}.")


def check_format(value: Any, name: str, digits: int) -> None:
    """Значение должно состоять ровно из `digits` цифр."""
    if value is None:
        return
    clean = str(value).strip()
    if not clean.isdigit() or len(clean) != digits:
        raise ValidationError(
            f"'{name}' должен содержать ровно {digits} цифр (получено: '{clean}')."
        )


def coerce_bool(args: dict[str, Any], *keys: str) -> None:
    """Преобразовать булевы значения в строку 'true'/None для Checko API."""
    for key in keys:
        value = args.get(key)
        if isinstance(value, bool):
            args[key] = "true" if value else None
