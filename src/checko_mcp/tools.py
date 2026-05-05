"""Реестр MCP-инструментов Checko: схемы, эндпоинты, пред-валидация."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ._validation import ValidationError as _ValidationError
from ._validation import check_format, coerce_bool, require_any

PreCall = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    endpoint: str
    description: str
    schema: dict[str, Any]
    pre: PreCall | None = field(default=None)


# ---------------------------------------------------------------------------
# Pre-call validators
# ---------------------------------------------------------------------------

def _search_pre(args: dict[str, Any]) -> None:
    if not args.get("query"):
        raise _ValidationError("Параметр 'query' обязателен.")
    if not args.get("by"):
        raise _ValidationError("Параметр 'by' обязателен (например, 'name' или 'okved').")
    if not args.get("obj"):
        raise _ValidationError("Параметр 'obj' обязателен (например, 'org').")


def _contracts_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)
    check_format(args.get("inn"), "inn", 10)
    if not args.get("law"):
        raise _ValidationError("Параметр 'law' обязателен ('44' или '223').")
    law_str = str(args["law"])
    if law_str not in ("44", "223"):
        raise _ValidationError(f"Параметр 'law' должен быть '44' или '223' (получено: '{law_str}').")
    args["law"] = law_str


def _company_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)
    check_format(args.get("inn"), "inn", 10)
    coerce_bool(args, "source")


def _entrepreneur_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrnip", "inn", "okpo")
    check_format(args.get("ogrnip"), "ogrnip", 15)
    check_format(args.get("inn"), "inn", 12)
    coerce_bool(args, "source")


def _person_pre(args: dict[str, Any]) -> None:
    check_format(args.get("inn"), "inn", 12)


def _finances_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)
    check_format(args.get("inn"), "inn", 10)
    coerce_bool(args, "extended")


def _legal_cases_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)
    check_format(args.get("inn"), "inn", 10)
    coerce_bool(args, "actual", "active")


def _id_required_pre(args: dict[str, Any]) -> None:
    """ОГРН/ИНН обязательны, форматы — стандартные (13/10)."""
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)
    check_format(args.get("inn"), "inn", 10)


def _bank_pre(args: dict[str, Any]) -> None:
    check_format(args.get("bic"), "bic", 9)


def _timeline_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)


def _fedresurs_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)


def _bankruptcy_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", 13)


# ---------------------------------------------------------------------------
# Schema fragments
# ---------------------------------------------------------------------------

_PAGE = {
    "limit": {"type": "integer", "description": "Количество элементов на страницу (макс. 100)"},
    "page": {"type": "integer", "description": "Номер страницы"},
}

_DATE_RANGE = {
    "date_from": {"type": "string", "description": "Дата от (формат YYYY-MM-DD)"},
    "date_to": {"type": "string", "description": "Дата до (формат YYYY-MM-DD)"},
}

_SORT_DATE = {
    "sort": {
        "type": "string",
        "description": "Сортировка: 'date' (по возрастанию) или '-date' (по убыванию)",
        "enum": ["date", "-date"],
    },
}


# ---------------------------------------------------------------------------
# Tools registry
# ---------------------------------------------------------------------------

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="search",
        endpoint="/search",
        description=(
            "Поиск организаций и ИП в реестрах ЕГРЮЛ/ЕГРИП. "
            "Обязательно укажите критерий поиска `by` (например, 'name' — по названию, "
            "'okved' — по коду деятельности) и тип объекта `obj` ('org' — юрлицо). "
            "Для поиска юрлица по ОГРН/ИНН используйте `get_company`, не `search`."
        ),
        schema={
            "type": "object",
            "properties": {
                "by": {
                    "type": "string",
                    "description": (
                        "Критерий поиска. Проверенные значения: 'name' — по наименованию, "
                        "'okved' — по коду ОКВЭД-2. Другие критерии могут быть отвергнуты API."
                    ),
                    "enum": ["name", "okved"],
                },
                "obj": {
                    "type": "string",
                    "description": "Тип объекта поиска. Сейчас API стабильно поддерживает 'org' (юрлицо).",
                    "enum": ["org"],
                },
                "query": {
                    "type": "string",
                    "description": "Строка поиска: название (для by='name') или код (для by='okved').",
                },
                "region": {
                    "type": "string",
                    "description": "Код региона РФ (например, '77' для Москвы) — дополнительный фильтр",
                },
                "codes": {
                    "type": "string",
                    "description": "Передайте 'all' для поиска по дополнительным кодам ОКВЭД-2 (v2.4)",
                },
                "date_from": {
                    "type": "string",
                    "description": "Дата регистрации от (формат YYYY-MM-DD)",
                },
                "date_to": {
                    "type": "string",
                    "description": "Дата регистрации до (формат YYYY-MM-DD)",
                },
                **_PAGE,
            },
            "required": ["by", "obj", "query"],
        },
        pre=_search_pre,
    ),
    ToolSpec(
        name="get_company",
        endpoint="/company",
        description=(
            "Получить сведения об организации из ЕГРЮЛ по ОГРН или ИНН. "
            "Возвращает основные данные, руководителей, учредителей, лицензии, "
            "налоги, реестр МСП, факторы риска и другую информацию."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации (13 цифр)"},
                "inn": {"type": "string", "description": "ИНН организации (10 цифр)"},
                "source": {
                    "type": "boolean",
                    "description": "Если true — возвращает исходные XML-данные ЕГРЮЛ",
                },
            },
        },
        pre=_company_pre,
    ),
    ToolSpec(
        name="get_entrepreneur",
        endpoint="/entrepreneur",
        description=(
            "Получить сведения об индивидуальном предпринимателе из ЕГРИП "
            "по ОГРНИП, ИНН или ОКПО. Возвращает данные ЕГРИП, лицензии, "
            "налоги, факторы риска и аффилированных лиц."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrnip": {
                    "type": "string",
                    "description": "ОГРНИП индивидуального предпринимателя (15 цифр)",
                },
                "inn": {
                    "type": "string",
                    "description": "ИНН физического лица — индивидуального предпринимателя (12 цифр)",
                },
                "okpo": {"type": "string", "description": "Код ОКПО предпринимателя"},
                "source": {
                    "type": "boolean",
                    "description": "Если true — возвращает исходные XML-данные ЕГРИП",
                },
            },
        },
        pre=_entrepreneur_pre,
    ),
    ToolSpec(
        name="get_person",
        endpoint="/person",
        description=(
            "Получить информацию о физическом лице по ИНН: "
            "связи с организациями (руководитель, учредитель), ИП, "
            "товарные знаки, банкротства, реестр недобросовестных поставщиков, "
            "санкции и массовые показатели ФНС."
        ),
        schema={
            "type": "object",
            "properties": {
                "inn": {"type": "string", "description": "ИНН физического лица (12 цифр)"},
            },
            "required": ["inn"],
        },
        pre=_person_pre,
    ),
    ToolSpec(
        name="get_finances",
        endpoint="/finances",
        description=(
            "Получить финансовую отчётность российской организации по ОГРН или ИНН "
            "(данные Росстата и ГИР БО ФНС, 2011–2023 гг.)."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации"},
                "inn": {"type": "string", "description": "ИНН организации"},
                "extended": {
                    "type": "boolean",
                    "description": "Если true — расширенная версия отчётности с детализацией по строкам",
                },
            },
        },
        pre=_finances_pre,
    ),
    ToolSpec(
        name="get_legal_cases",
        endpoint="/legal-cases",
        description=(
            "Получить арбитражные дела с участием организации или ИП "
            "по ОГРН/ОГРНИП или ИНН. Поддерживает фильтрацию по роли, "
            "датам, статусу, сумме иска и постраничный вывод."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации или ОГРНИП предпринимателя"},
                "inn": {"type": "string", "description": "ИНН организации или предпринимателя"},
                "role": {
                    "type": "string",
                    "description": "Роль в деле: 'plaintiff' (истец) или 'defendant' (ответчик)",
                    "enum": ["plaintiff", "defendant"],
                },
                "actual": {
                    "type": "boolean",
                    "description": "Если true — только актуальные дела (без отклонённых и прекращённых)",
                },
                "active": {
                    "type": "boolean",
                    "description": "Если true — только активные (незавершённые) дела",
                },
                **_DATE_RANGE,
                "claim_amount_from": {
                    "type": "number",
                    "description": "Минимальная сумма исковых требований, руб.",
                },
                "claim_amount_to": {
                    "type": "number",
                    "description": "Максимальная сумма исковых требований, руб.",
                },
                **_PAGE,
                **_SORT_DATE,
            },
        },
        pre=_legal_cases_pre,
    ),
    ToolSpec(
        name="get_contracts",
        endpoint="/contracts",
        description=(
            "Получить государственные контракты по 44-ФЗ или 223-ФЗ "
            "с участием организации или ИП. Параметр `law` обязателен — "
            "API возвращает контракты только по одному закону за вызов."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации"},
                "inn": {"type": "string", "description": "ИНН организации"},
                "law": {
                    "type": "string",
                    "description": "Закон о госзакупках: '44' (44-ФЗ) или '223' (223-ФЗ). Обязателен.",
                    "enum": ["44", "223"],
                },
                "role": {
                    "type": "string",
                    "description": "Роль: 'customer' (заказчик) или 'supplier' (поставщик)",
                    "enum": ["customer", "supplier"],
                },
                **_PAGE,
            },
            "required": ["law"],
        },
        pre=_contracts_pre,
    ),
    ToolSpec(
        name="get_inspections",
        endpoint="/inspections",
        description=(
            "Получить сведения о проверках (плановых и внеплановых) "
            "в отношении организации или ИП по ОГРН или ИНН."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации"},
                "inn": {"type": "string", "description": "ИНН организации"},
                **_PAGE,
            },
        },
        pre=_id_required_pre,
    ),
    ToolSpec(
        name="get_bank",
        endpoint="/bank",
        description=(
            "Получить информацию о банке или кредитной организации РФ по БИК. "
            "Возвращает наименование, адрес, корреспондентский и расчётные счета."
        ),
        schema={
            "type": "object",
            "properties": {
                "bic": {
                    "type": "string",
                    "description": "БИК банка или кредитной организации (9 цифр)",
                },
            },
            "required": ["bic"],
        },
        pre=_bank_pre,
    ),
    ToolSpec(
        name="get_timeline",
        endpoint="/timeline",
        description=(
            "Получить историю основных изменений организации, ИП или "
            "аффилированного физлица по ОГРН/ОГРНИП или ИНН. "
            "Для физлица укажите ИНН, чтобы получить полную историю. (v2.4)"
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации или ОГРНИП предпринимателя"},
                "inn": {
                    "type": "string",
                    "description": "ИНН организации, предпринимателя или физлица",
                },
            },
        },
        pre=_timeline_pre,
    ),
    ToolSpec(
        name="get_fedresurs",
        endpoint="/fedresurs",
        description=(
            "Получить сообщения Федресурса (ЕФРСФДЮЛ) по организации или ИП. "
            "Поддерживает фильтрацию по типу сообщения, роли, датам и постраничный вывод. (v2.4)"
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации или ОГРНИП предпринимателя"},
                "inn": {"type": "string", "description": "ИНН организации или предпринимателя"},
                "type": {
                    "type": "string",
                    "description": "Тип сообщения Федресурса (например, 'CreditorIntentionGoToCourt')",
                },
                "role": {
                    "type": "string",
                    "description": "Роль: 'all' (все, по умолчанию) или 'publisher' (только публикатор)",
                    "enum": ["all", "publisher"],
                },
                **_DATE_RANGE,
                **_PAGE,
                **_SORT_DATE,
            },
        },
        pre=_fedresurs_pre,
    ),
    ToolSpec(
        name="get_bankruptcy_messages",
        endpoint="/bankruptcy-messages",
        description=(
            "Получить записи ЕФРСБ (Единого федерального реестра сведений о банкротстве) "
            "по организации, ИП или физлицу. Поддерживает фильтрацию по датам и постраничный вывод. (v2.4)"
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {"type": "string", "description": "ОГРН организации или ОГРНИП предпринимателя"},
                "inn": {
                    "type": "string",
                    "description": "ИНН организации, предпринимателя или физлица",
                },
                **_DATE_RANGE,
                **_PAGE,
                **_SORT_DATE,
            },
        },
        pre=_bankruptcy_pre,
    ),
]


TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}
