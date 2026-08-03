"""Валидаторы и хелперы для аргументов MCP-инструментов."""

from typing import Any


class ValidationError(Exception):
    """Ошибка валидации аргументов инструмента."""


def require_any(args: dict[str, Any], *keys: str) -> None:
    """Хотя бы один из ключей должен присутствовать и быть истинным."""
    if not any(args.get(k) for k in keys):
        names = " или ".join(f"'{k}'" for k in keys)
        raise ValidationError(f"Необходимо указать {names}.")


def check_format(value: Any, name: str, *lengths: int) -> None:
    """Значение должно состоять из цифр, а его длина — совпадать с одной из `lengths`.

    Несколько длин нужны там, где эндпоинт работает и с организациями, и с ИП или
    физлицами: ИНН бывает 10 цифр (юрлицо) или 12 (ИП, физлицо), а ОГРН — 13 цифр
    у организации или 15 у предпринимателя (ОГРНИП). Проверяется только
    правдоподобность формата: сужать то, что API принимает, нельзя.
    """
    if value is None:
        return
    clean = str(value).strip()
    if not clean.isdigit() or len(clean) not in lengths:
        expected = (
            f"ровно {lengths[0]}" if len(lengths) == 1 else " или ".join(map(str, lengths))
        )
        raise ValidationError(
            f"'{name}' должен содержать {expected} цифр (получено: '{clean}')."
        )


_TRUE_STRINGS = frozenset({"true", "1", "yes", "да"})
_FALSE_STRINGS = frozenset({"false", "0", "no", "нет", ""})


def coerce_bool(args: dict[str, Any], *keys: str) -> None:
    """Привести булевы флаги к виду, который понимает Checko API.

    API распознаёт только строку `"true"`; параметр со значением `false` нужно
    убирать из запроса целиком, иначе строка `"false"` трактуется как включённый
    флаг. Строковые значения обрабатываются наравне с булевыми: MCP-клиент может
    прислать `"true"` вместо `true`.
    """
    for key in keys:
        value = args.get(key)
        if isinstance(value, bool):
            args[key] = "true" if value else None
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUE_STRINGS:
                args[key] = "true"
            elif lowered in _FALSE_STRINGS:
                args[key] = None
            else:
                raise ValidationError(
                    f"'{key}' должен быть булевым значением (получено: '{value}')."
                )
