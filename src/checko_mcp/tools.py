"""Реестр MCP-инструментов Checko: схемы, эндпоинты, пред-валидация.

Параметры сверены со страницами методов документации Checko API 2.4
(`https://checko.ru/integration/api/<метод>`). Правило: схема инструмента не должна
объявлять параметры, которых у метода нет, и не должна сужать допустимые значения —
иначе агент либо получает молча неотфильтрованный ответ, либо теряет доступ
к работающей возможности API.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ._validation import ValidationError as _ValidationError
from ._validation import check_format, coerce_bool, require_any

PreCall = Callable[[dict[str, Any]], None]

# Длины идентификаторов. ОГРН организации — 13 цифр, ОГРНИП предпринимателя — 15;
# ИНН юрлица — 10, ИНН физлица (в том числе ИП) — 12.
_ORG_OGRN = (13,)
_ORG_INN = (10,)
_ANY_OGRN = (13, 15)
_ANY_INN = (10, 12)
_PERSON_INN = (12,)
_ENT_OGRNIP = (15,)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    endpoint: str
    title: str
    description: str
    schema: dict[str, Any]
    pre: PreCall | None = field(default=None)


# ---------------------------------------------------------------------------
# Pre-call validators
# ---------------------------------------------------------------------------

def _search_pre(args: dict[str, Any]) -> None:
    for key, hint in (
        ("by", "например, 'name' — по наименованию"),
        ("obj", "'org' — организация, 'ent' — ИП"),
        ("query", "текст поискового запроса"),
    ):
        if not args.get(key):
            raise _ValidationError(f"Параметр '{key}' обязателен ({hint}).")
    coerce_bool(args, "active")


def _company_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn", "okpo")
    check_format(args.get("ogrn"), "ogrn", *_ORG_OGRN)
    check_format(args.get("inn"), "inn", *_ORG_INN)
    coerce_bool(args, "source")


def _entrepreneur_pre(args: dict[str, Any]) -> None:
    # У метода /entrepreneur параметр называется `ogrn`, хотя несёт ОГРНИП.
    # Псевдоним оставлен, чтобы вызов с `ogrnip` не проваливался молча.
    if args.get("ogrnip") and not args.get("ogrn"):
        args["ogrn"] = args["ogrnip"]
    args.pop("ogrnip", None)

    require_any(args, "ogrn", "inn", "okpo")
    check_format(args.get("ogrn"), "ogrn", *_ENT_OGRNIP)
    check_format(args.get("inn"), "inn", *_PERSON_INN)
    coerce_bool(args, "source")


def _person_pre(args: dict[str, Any]) -> None:
    if not args.get("inn"):
        raise _ValidationError("Параметр 'inn' обязателен (ИНН физлица, 12 цифр).")
    check_format(args.get("inn"), "inn", *_PERSON_INN)


def _finances_pre(args: dict[str, Any]) -> None:
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", *_ORG_OGRN)
    check_format(args.get("inn"), "inn", *_ORG_INN)
    coerce_bool(args, "extended")


def _subject_pre(args: dict[str, Any]) -> None:
    """Эндпоинты, работающие и с организациями, и с ИП или физлицами."""
    require_any(args, "ogrn", "inn")
    check_format(args.get("ogrn"), "ogrn", *_ANY_OGRN)
    check_format(args.get("inn"), "inn", *_ANY_INN)


def _legal_cases_pre(args: dict[str, Any]) -> None:
    _subject_pre(args)
    coerce_bool(args, "actual", "active")


def _contracts_pre(args: dict[str, Any]) -> None:
    _subject_pre(args)
    if not args.get("law"):
        raise _ValidationError("Параметр 'law' обязателен ('44', '94' или '223').")
    law = str(args["law"]).strip()
    if law not in ("44", "94", "223"):
        raise _ValidationError(
            f"Параметр 'law' должен быть '44', '94' или '223' (получено: '{law}')."
        )
    args["law"] = law


def _bank_pre(args: dict[str, Any]) -> None:
    if not args.get("bic"):
        raise _ValidationError("Параметр 'bic' обязателен (БИК, 9 цифр).")
    check_format(args.get("bic"), "bic", 9)


# ---------------------------------------------------------------------------
# Schema fragments
# ---------------------------------------------------------------------------

_PAGE = {
    "limit": {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "description": "Записей на страницу (по умолчанию и максимум — 100)",
    },
    "page": {"type": "integer", "minimum": 1, "description": "Номер страницы"},
}

_DATE_RANGE = {
    "date_from": {"type": "string", "description": "Дата от, формат YYYY-MM-DD"},
    "date_to": {"type": "string", "description": "Дата до, формат YYYY-MM-DD"},
}

_SORT_DATE = {
    "sort": {
        "type": "string",
        "description": "Сортировка по дате: 'date' — по возрастанию, '-date' — по убыванию",
        "enum": ["date", "-date"],
    },
}

_SUBJECT_ID = {
    "ogrn": {
        "type": "string",
        "description": "ОГРН организации (13 цифр) или ОГРНИП предпринимателя (15 цифр)",
    },
    "inn": {
        "type": "string",
        "description": "ИНН: 10 цифр у организации, 12 у ИП или физлица",
    },
}

_ORG_ID = {
    "ogrn": {"type": "string", "description": "ОГРН организации (13 цифр)"},
    "inn": {"type": "string", "description": "ИНН организации (10 цифр)"},
}

_NOT_BELARUS = (
    "Работает только по российским реестрам: белорусские организации (УНП) "
    "через это API недоступны."
)


# ---------------------------------------------------------------------------
# Tools registry
# ---------------------------------------------------------------------------

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="search",
        endpoint="/search",
        title="Поиск в ЕГРЮЛ/ЕГРИП",
        description=(
            "Текстовый поиск организаций и ИП в ЕГРЮЛ/ЕГРИП. Обязательны `by` (что ищем), "
            "`obj` ('org' — организация, 'ent' — ИП) и `query`.\n"
            "Ключевые режимы: `by='name'` — по наименованию или ФИО предпринимателя; "
            "`by='founder-name'` — найти все организации, где человек или компания "
            "числится учредителем; `by='leader-name'` — где человек руководитель; "
            "`by='okved'` — по коду вида деятельности; `by='reg-date'` и `by='upd-date'` — "
            "по дате регистрации или обновления выписки (в `query` передаётся дата "
            "YYYY-MM-DD).\n"
            "Если ОГРН или ИНН уже известен — вызывайте `get_company` или "
            "`get_entrepreneur` напрямую, поиск для этого не нужен. "
            "Минимум 4 символа при поиске по наименованию или ФИО. " + _NOT_BELARUS
        ),
        schema={
            "type": "object",
            "properties": {
                "by": {
                    "type": "string",
                    "description": "Критерий поиска",
                    "enum": [
                        "name",
                        "founder-name",
                        "leader-name",
                        "okved",
                        "reg-date",
                        "upd-date",
                    ],
                },
                "obj": {
                    "type": "string",
                    "description": "Что искать: 'org' — организации, 'ent' — ИП",
                    "enum": ["org", "ent"],
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Текст запроса: наименование, ФИО, код ОКВЭД-2 "
                        "или дата YYYY-MM-DD для by='reg-date'/'upd-date'"
                    ),
                },
                "region": {
                    "type": "string",
                    "description": "Код региона РФ, 2 цифры (например, '77' — Москва)",
                },
                "okved": {
                    "type": "string",
                    "description": (
                        "Фильтр по основному коду ОКВЭД-2. Не применяется при by='okved'"
                    ),
                },
                "opf": {
                    "type": "string",
                    "description": (
                        "Код организационно-правовой формы по ОКОПФ, 2 или 5 цифр. "
                        "Не применяется при by='name' и при obj='ent'"
                    ),
                },
                "active": {
                    "type": "boolean",
                    "description": "true — только действующие организации и ИП",
                },
                "codes": {
                    "type": "string",
                    "description": (
                        "'all' — при by='okved' искать и по дополнительным кодам ОКВЭД-2"
                    ),
                    "enum": ["all"],
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
        title="Организация (ЕГРЮЛ)",
        description=(
            "Сведения об организации из ЕГРЮЛ по ОГРН, ИНН или ОКПО: статус, реквизиты, "
            "адрес, руководители, учредители и связи через них, лицензии, налоги, "
            "реестр МСП, товарные знаки и факторы риска (санкции, недобросовестный "
            "поставщик, массовый адрес или руководитель, обременения, записи ЕФРСБ).\n"
            "Предпочитайте ОГРН: ИНН не уникален при наличии филиалов, и API вернёт "
            "головную организацию. " + _NOT_BELARUS
        ),
        schema={
            "type": "object",
            "properties": {
                **_ORG_ID,
                "okpo": {
                    "type": "string",
                    "description": "Код ОКПО организации (если нет ни ОГРН, ни ИНН)",
                },
                "source": {
                    "type": "boolean",
                    "description": (
                        "true — добавить исходный набор данных ЕГРЮЛ от ФНС. "
                        "Ответ становится очень объёмным: включайте только когда нужны "
                        "поля, которых нет в основном ответе"
                    ),
                },
            },
        },
        pre=_company_pre,
    ),
    ToolSpec(
        name="get_entrepreneur",
        endpoint="/entrepreneur",
        title="Индивидуальный предприниматель (ЕГРИП)",
        description=(
            "Сведения об индивидуальном предпринимателе из ЕГРИП по ОГРНИП, ИНН (12 цифр) "
            "или ОКПО: статус, виды деятельности, лицензии, налоговые режимы, реестр МСП, "
            "товарные знаки, факторы риска и записи ЕФРСБ.\n"
            "Если ИНН относится к физлицу без действующего ИП — используйте `get_person`. "
            + _NOT_BELARUS
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": {
                    "type": "string",
                    "description": "ОГРНИП предпринимателя (15 цифр)",
                },
                "inn": {"type": "string", "description": "ИНН предпринимателя (12 цифр)"},
                "okpo": {
                    "type": "string",
                    "description": "Код ОКПО (если нет ни ОГРНИП, ни ИНН)",
                },
                "source": {
                    "type": "boolean",
                    "description": (
                        "true — добавить исходный набор данных ЕГРИП от ФНС. "
                        "Существенно увеличивает объём ответа"
                    ),
                },
            },
        },
        pre=_entrepreneur_pre,
    ),
    ToolSpec(
        name="get_person",
        endpoint="/person",
        title="Физическое лицо",
        description=(
            "Информация о физическом лице по ИНН (12 цифр): связи с организациями "
            "в роли руководителя и учредителя, ИП, товарные знаки, записи ЕФРСБ, "
            "реестр недобросовестных поставщиков, санкции и массовые показатели ФНС.\n"
            "Физлицо ищется только по ИНН — поиска по ФИО у этого метода нет. Чтобы найти "
            "организации по ФИО, используйте `search` с by='founder-name' или "
            "by='leader-name'.\n"
            "Обработка данных физлиц ограничена 152-ФЗ: перед использованием прочитайте "
            "ресурс checko://docs/legal и убедитесь в наличии законного основания."
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
        title="Финансовая отчётность",
        description=(
            "Финансовая отчётность организации по ОГРН или ИНН — данные Росстата и ГИР БО "
            "ФНС, доступны с 2011 года. Отчётность сдают только юридические лица: "
            "у ИП её нет.\n"
            "Ключевые строки: 2110 — выручка, 2400 — чистая прибыль, 1300 — капитал "
            "(отрицательный означает превышение обязательств над активами), "
            "1400 и 1500 — долгосрочные и краткосрочные обязательства."
        ),
        schema={
            "type": "object",
            "properties": {
                **_ORG_ID,
                "extended": {
                    "type": "boolean",
                    "description": "true — расширенная отчётность с детализацией по строкам",
                },
            },
        },
        pre=_finances_pre,
    ),
    ToolSpec(
        name="get_legal_cases",
        endpoint="/legal-cases",
        title="Арбитражные дела",
        description=(
            "Арбитражные дела организации или ИП из Картотеки арбитражных дел. "
            "Возвращает в том числе `ОбщСуммИск` — суммарную цену иска.\n"
            "Для оценки риска смотрите роль ответчика: "
            "role='defendant' вместе с actual=true и active=true. "
            "Данные КАД обновляются с задержкой порядка одной-двух недель."
        ),
        schema={
            "type": "object",
            "properties": {
                **_SUBJECT_ID,
                "role": {
                    "type": "string",
                    "description": "Роль: 'plaintiff' — истец, 'defendant' — ответчик",
                    "enum": ["plaintiff", "defendant"],
                },
                "actual": {"type": "boolean", "description": "true — только актуальные дела"},
                "active": {
                    "type": "boolean",
                    "description": "true — только активные (незавершённые) дела",
                },
                **_DATE_RANGE,
                "claim_amount_from": {
                    "type": "number",
                    "description": "Минимальная сумма иска, руб.",
                },
                "claim_amount_to": {
                    "type": "number",
                    "description": "Максимальная сумма иска, руб.",
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
        title="Госзакупки",
        description=(
            "Контракты по 44-ФЗ и 94-ФЗ и договоры по 223-ФЗ для организации или ИП. "
            "Параметр `law` обязателен — API отдаёт данные строго по одному закону "
            "за вызов, поэтому за полной картиной нужно несколько вызовов.\n"
            "Сортировка `sort='-price'` даёт крупнейшие контракты первыми — это самый "
            "быстрый способ оценить масштаб участника закупок."
        ),
        schema={
            "type": "object",
            "properties": {
                **_SUBJECT_ID,
                "law": {
                    "type": "string",
                    "description": "Закон: '44' (44-ФЗ), '94' (94-ФЗ) или '223' (223-ФЗ)",
                    "enum": ["44", "94", "223"],
                },
                "role": {
                    "type": "string",
                    "description": "Роль: 'customer' — заказчик, 'supplier' — поставщик",
                    "enum": ["customer", "supplier"],
                },
                "sort": {
                    "type": "string",
                    "description": (
                        "Сортировка: 'date'/'-date' — по дате, 'price'/'-price' — по сумме"
                    ),
                    "enum": ["date", "-date", "price", "-price"],
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
        title="Проверки",
        description=(
            "Проверки (контрольно-надзорные мероприятия) организации или ИП по данным "
            "ФГИС «Единый реестр проверок» Генпрокуратуры РФ. Важны выявленные нарушения "
            "и их повторяемость, а не само число проверок."
        ),
        schema={
            "type": "object",
            "properties": {**_SUBJECT_ID, **_PAGE, **_SORT_DATE},
        },
        pre=_subject_pre,
    ),
    ToolSpec(
        name="get_enforcements",
        endpoint="/enforcements",
        title="Исполнительные производства (ФССП)",
        description=(
            "Исполнительные производства, открытые в отношении организации, по данным "
            "ФССП. Возвращает номер производства, предмет исполнения, сумму долга "
            "и непогашенный остаток, отдел судебных приставов.\n"
            "Это один из самых показательных сигналов платёжной дисциплины: открытые "
            "производства означают, что долг уже взыскивается приставами. "
            "Проверять вместе с `get_legal_cases`: иск показывает требование, "
            "исполнительное производство — что решение вступило в силу и не исполнено."
        ),
        schema={
            "type": "object",
            "properties": {**_SUBJECT_ID, **_PAGE, **_SORT_DATE},
        },
        pre=_subject_pre,
    ),
    ToolSpec(
        name="get_bank",
        endpoint="/bank",
        title="Банк по БИК",
        description=(
            "Информация о банке или кредитной организации РФ по БИК (9 цифр) по данным "
            "ЦБ РФ: наименование, адрес, корреспондентский счёт, статус лицензии. "
            "Используйте для сверки платёжных реквизитов: БИК должен соответствовать "
            "действующему банку, а расчётный счёт — его корреспондентскому счёту."
        ),
        schema={
            "type": "object",
            "properties": {
                "bic": {"type": "string", "description": "БИК банка (9 цифр)"},
            },
            "required": ["bic"],
        },
        pre=_bank_pre,
    ),
    ToolSpec(
        name="get_timeline",
        endpoint="/timeline",
        title="История изменений",
        description=(
            "Хронология основных изменений организации, ИП или аффилированного физлица "
            "по ОГРН/ОГРНИП или ИНН: смена руководителя, состава учредителей, адреса, "
            "наименования, статуса.\n"
            "Незаменима, чтобы понять последовательность событий: например, что смена "
            "руководителя произошла уже после подачи иска."
        ),
        schema={
            "type": "object",
            "properties": {
                "ogrn": _SUBJECT_ID["ogrn"],
                "inn": {
                    "type": "string",
                    "description": (
                        "ИНН организации (10 цифр), ИП или физлица (12 цифр)"
                    ),
                },
            },
        },
        pre=_subject_pre,
    ),
    ToolSpec(
        name="get_fedresurs",
        endpoint="/fedresurs",
        title="Сообщения Федресурса",
        description=(
            "Сообщения Федресурса (ЕФРСФДЮЛ) по организации или ИП с фильтрами по типу, "
            "роли и датам.\n"
            "Наиболее значимые типы: 'CreditorIntentionGoToCourt' — намерение кредитора "
            "обратиться в суд с заявлением о банкротстве (ранний сигнал, опережающий "
            "само дело), 'PledgeAgreement' — договор залога."
        ),
        schema={
            "type": "object",
            "properties": {
                **_SUBJECT_ID,
                "type": {
                    "type": "string",
                    "description": (
                        "Тип сообщения Федресурса, например 'CreditorIntentionGoToCourt'"
                    ),
                },
                "role": {
                    "type": "string",
                    "description": (
                        "Роль субъекта: 'all' — любая (по умолчанию), "
                        "'publisher' — только публикатор"
                    ),
                    "enum": ["all", "publisher"],
                },
                **_DATE_RANGE,
                **_PAGE,
                **_SORT_DATE,
            },
        },
        pre=_subject_pre,
    ),
    ToolSpec(
        name="get_bankruptcy_messages",
        endpoint="/bankruptcy-messages",
        title="Записи ЕФРСБ (банкротство)",
        description=(
            "Записи Единого федерального реестра сведений о банкротстве (ЕФРСБ) "
            "по юридическому или физическому лицу с фильтром по датам.\n"
            "Наличие записей означает открытую или завершённую процедуру банкротства — "
            "это блокирующий фактор для работы с контрагентом."
        ),
        schema={
            "type": "object",
            "properties": {
                **_SUBJECT_ID,
                **_DATE_RANGE,
                **_PAGE,
                **_SORT_DATE,
            },
        },
        pre=_subject_pre,
    ),
]


TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}
