"""Сжатие ответов Checko API до размера, пригодного для контекста агента.

Зачем. MCP-клиент ограничивает объём вывода инструмента: Claude Code предупреждает
на 10 000 токенах и обрезает на 25 000. Замеры на реальном API показали, что это
не теоретическая проблема, а обычное дело:

    /finances?extended=true          151 597 символов   (~50 000 токенов)
    /search?by=name                  108 191            (~36 000)
    /company (крупная организация)   113 081            (~37 000)
    /contracts?law=94                 92 470            (~30 000)
    /enforcements                     59 106            (~19 000)

Обрезка происходит молча: агент получает оборванный JSON и достраивает недостающее
домыслом. Поэтому сжатие включено по умолчанию, а полный ответ отдаётся по явному
запросу `detail="full"`.

Как. Никакого белого списка полей: он молча потерял бы поля, которые Checko добавит
в следующей версии API, а именно скалярные поля несут факторы риска. Вместо этого
длинные списки сворачиваются до нескольких первых элементов, а сколько всего было —
сообщается рядом. Все скалярные поля сохраняются полностью.

Исключение — `/finances`: там расширенная отчётность это около 150 строк формы
за каждый год, и в сжатом виде осмысленно оставить только ключевые строки.
"""

from typing import Any

COMPACT = "compact"
FULL = "full"

# Сколько элементов оставлять: у основного списка записей и у вложенных справочных
# списков вроде лицензий или товарных знаков.
RECORD_LIMIT = 20
NESTED_LIMIT = 5

# Ключи, которые несут основной список записей эндпоинта.
_RECORD_KEYS = frozenset({"Записи", "СписДел"})

# Ключевые строки бухгалтерского баланса и отчёта о финансовых результатах.
FINANCE_KEY_LINES: dict[str, str] = {
    "1150": "Основные средства",
    "1200": "Оборотные активы",
    "1230": "Дебиторская задолженность",
    "1250": "Денежные средства",
    "1300": "Капитал и резервы (отрицательный — признак банкротства)",
    "1400": "Долгосрочные обязательства",
    "1500": "Краткосрочные обязательства",
    "1600": "Баланс активов",
    "2110": "Выручка",
    "2200": "Прибыль от продаж",
    "2400": "Чистая прибыль (убыток)",
}

# Порог, после которого стоит предупредить о приближении к суточному лимиту
# бесплатного тарифа (100 запросов в сутки).
DAILY_FREE_LIMIT = 100
DAILY_WARN_AT = 90


class Collapsed:
    """Счётчик свёрнутого — что и на сколько урезано."""

    def __init__(self) -> None:
        self.items: dict[str, int] = {}

    def note(self, path: str, total: int) -> None:
        self.items[path] = total

    def __bool__(self) -> bool:
        return bool(self.items)


def _collapse(value: Any, path: str, collapsed: Collapsed) -> Any:
    if isinstance(value, dict):
        return {k: _collapse(v, f"{path}.{k}" if path else k, collapsed) for k, v in value.items()}

    if isinstance(value, list):
        key = path.rsplit(".", 1)[-1]
        limit = RECORD_LIMIT if key in _RECORD_KEYS or not path else NESTED_LIMIT
        if len(value) > limit:
            collapsed.note(path or "data", len(value))
            value = value[:limit]
        return [_collapse(item, path, collapsed) for item in value]

    return value


def _shape_finances(data: Any, collapsed: Collapsed) -> Any:
    """Оставить только ключевые строки отчётности по каждому году."""
    if not isinstance(data, dict):
        return _collapse(data, "", collapsed)

    result: dict[str, Any] = {}
    dropped = 0
    for year, lines in data.items():
        if not isinstance(lines, dict):
            result[year] = lines
            continue
        kept = {code: lines[code] for code in FINANCE_KEY_LINES if code in lines}
        if kept:
            dropped += len(lines) - len(kept)
            result[year] = kept
        else:
            result[year] = lines

    if dropped:
        collapsed.note("строки отчётности (оставлены ключевые)", dropped)
    return result


def shape(endpoint: str, payload: dict[str, Any], detail: str) -> dict[str, Any]:
    """Вернуть ответ API в запрошенной степени детализации.

    `detail="full"` отдаёт ответ без изменений. `detail="compact"` сворачивает
    длинные списки и добавляет блок `сжатие` с описанием того, что урезано.
    """
    if detail == FULL:
        return payload

    collapsed = Collapsed()
    result: dict[str, Any] = {}

    for key, value in payload.items():
        if key == "data":
            if endpoint == "/finances":
                result[key] = _shape_finances(value, collapsed)
            else:
                result[key] = _collapse(value, "", collapsed)
        else:
            result[key] = value

    notes: list[str] = []
    if collapsed:
        notes.append("Списки урезаны. Полный ответ — тот же вызов с detail=\"full\".")

    meta = payload.get("meta")
    if isinstance(meta, dict):
        used = meta.get("today_request_count")
        if isinstance(used, int) and used >= DAILY_WARN_AT:
            notes.append(
                f"Израсходовано запросов за сутки: {used} из {DAILY_FREE_LIMIT} "
                "бесплатных. Дальше запросы либо платные, либо вернут ошибку лимита."
            )

    if collapsed or notes:
        block: dict[str, Any] = {"режим": COMPACT}
        if collapsed:
            block["свёрнуто_всего_элементов"] = collapsed.items
        if notes:
            block["примечания"] = notes
        result["сжатие"] = block

    return result
