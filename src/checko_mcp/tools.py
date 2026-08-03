"""Реестр MCP-инструментов Checko: схемы, эндпоинты, пред-валидация.

Параметры сверены со страницами методов документации Checko API 2.4
(`https://checko.ru/integration/api/<метод>`). Правило: схема инструмента не должна
объявлять параметры, которых у метода нет, и не должна сужать допустимые значения —
иначе агент либо получает молча неотфильтрованный ответ, либо теряет доступ
к работающей возможности API.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import _reports
from ._validation import ValidationError as _ValidationError
from ._validation import check_format, coerce_bool, require_any

PreCall = Callable[[dict[str, Any]], None]
# Каскадный обработчик: сам решает, какие эндпоинты вызвать и что вернуть.
Handler = Callable[[Any, dict[str, Any], str], Awaitable[dict[str, Any]]]

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
    """Инструмент — либо тонкая обёртка над одним методом API (`endpoint`),
    либо каскад, сам обращающийся к нескольким методам (`handler`)."""

    name: str
    title: str
    description: str
    schema: dict[str, Any]
    endpoint: str | None = field(default=None)
    pre: PreCall | None = field(default=None)
    handler: Handler | None = field(default=None)

    def __post_init__(self) -> None:
        if bool(self.endpoint) == bool(self.handler):
            raise ValueError(f"{self.name}: нужно указать ровно одно — endpoint или handler.")


# ---------------------------------------------------------------------------
# Pre-call validators
# ---------------------------------------------------------------------------

def _resolve_pre(args: dict[str, Any]) -> None:
    if not str(args.get("query") or "").strip():
        raise _ValidationError("Параметр 'query' обязателен.")
    coerce_bool(args, "active")


def _profile_pre(args: dict[str, Any]) -> None:
    if not str(args.get("identifier") or "").strip():
        raise _ValidationError(
            "Параметр 'identifier' обязателен: ОГРН, ОГРНИП, ИНН, ОКПО или БИК. "
            "Если известно только наименование или ФИО — сначала вызовите `resolve`."
        )
    coerce_bool(args, "source")


def _report_pre(args: dict[str, Any]) -> None:
    if not str(args.get("identifier") or "").strip():
        raise _ValidationError(
            "Параметр 'identifier' обязателен: ОГРН, ОГРНИП или ИНН проверяемого субъекта."
        )


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
        name="resolve",
        title="Найти субъекта",
        description=(
            "Точка входа. Принимает что угодно: наименование, ФИО, ОГРН, ОГРНИП, ИНН, "
            "ОКПО или БИК — и возвращает короткий список кандидатов с идентификаторами.\n"
            "Если передан идентификатор (только цифры), вид субъекта определяется по числу "
            "цифр, и сразу возвращается его карточка-минимум. Если передан текст — идёт "
            "поиск по ЕГРЮЛ/ЕГРИП.\n"
            "Режимы `by`: 'name' — по наименованию организации или ФИО предпринимателя; "
            "'founder-name' — все организации, где человек или компания числится "
            "учредителем; 'leader-name' — где человек руководитель; 'okved' — по коду "
            "деятельности; 'reg-date' и 'upd-date' — по дате (дата передаётся в `query`).\n"
            "Поиск по учредителю и руководителю — основной способ раскрутить связи "
            "человека, когда его ИНН неизвестен. Однофамильцы неизбежны: сверяйте "
            "найденное с другими признаками, прежде чем утверждать, что это тот же человек.\n"
            "Дальше берите полную карточку через `profile` или сразу отчёт через "
            "`due_diligence_report`. " + _NOT_BELARUS
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Наименование, ФИО, идентификатор или дата YYYY-MM-DD. "
                        "Минимум 4 символа при поиске по наименованию или ФИО"
                    ),
                },
                "by": {
                    "type": "string",
                    "description": "Критерий текстового поиска, по умолчанию 'name'",
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
                    "description": "Что искать: 'org' — организации (по умолчанию), 'ent' — ИП",
                    "enum": ["org", "ent"],
                },
                "region": {
                    "type": "string",
                    "description": "Код региона РФ, 2 цифры (например, '77' — Москва)",
                },
                "okved": {"type": "string", "description": "Фильтр по коду ОКВЭД-2"},
                "opf": {
                    "type": "string",
                    "description": (
                        "Код ОКОПФ, 2 или 5 цифр. Не применяется при by='name' и obj='ent'"
                    ),
                },
                "active": {
                    "type": "boolean",
                    "description": "true — только действующие организации и ИП",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Сколько кандидатов вернуть, по умолчанию 10",
                },
            },
            "required": ["query"],
        },
        pre=_resolve_pre,
        handler=_reports.resolve,
    ),
    ToolSpec(
        name="profile",
        title="Карточка субъекта",
        description=(
            "Полная карточка субъекта по одному идентификатору. Вид субъекта и нужный "
            "метод API определяются автоматически по числу цифр, угадывать не нужно:\n"
            "8 — ОКПО, 9 — БИК банка, 10 — ИНН организации, 12 — ИНН физлица, "
            "13 — ОГРН организации, 15 — ОГРНИП предпринимателя.\n"
            "ИНН из 12 цифр разбирается так: сначала ЕГРИП, и если действующего ИП нет — "
            "данные физлица и его связи с организациями. Обработка данных физлиц "
            "ограничена 152-ФЗ: убедитесь в наличии законного основания, см. ресурс "
            "checko://docs/legal.\n"
            "Что внутри: статус, реквизиты, адрес, руководители, учредители и связи через "
            "них, лицензии, налоги, реестр МСП, товарные знаки и факторы риска — санкции, "
            "недобросовестный поставщик, массовый адрес или руководитель, записи ЕФРСБ.\n"
            "Предпочитайте ОГРН: ИНН не уникален при наличии филиалов, и API вернёт "
            "головную организацию. Параметр `kind` нужен только чтобы принудительно "
            "выбрать метод — например, получить физлицо, минуя проверку ЕГРИП. "
            + _NOT_BELARUS
        ),
        schema={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "ОГРН, ОГРНИП, ИНН, ОКПО или БИК. Только цифры — наименование "
                        "и ФИО передавайте в `resolve`"
                    ),
                },
                "kind": {
                    "type": "string",
                    "description": (
                        "Принудительно выбрать вид субъекта вместо автоопределения: "
                        "'org' — организация, 'entrepreneur' — ИП, 'person' — физлицо, "
                        "'bank' — банк"
                    ),
                    "enum": ["org", "entrepreneur", "person", "bank"],
                },
                "source": {
                    "type": "boolean",
                    "description": (
                        "true — добавить исходный набор данных ФНС. Ответ становится очень "
                        'объёмным, поэтому требует detail="full"'
                    ),
                },
            },
            "required": ["identifier"],
        },
        pre=_profile_pre,
        handler=_reports.profile,
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
    ToolSpec(
        name="due_diligence_report",
        title="Отчёт: проверка контрагента",
        description=(
            "Полная проверка контрагента одним вызовом. Сам определяет вид субъекта, "
            "параллельно опрашивает реестры и возвращает сводку с посчитанными сигналами "
            "вместо шести сырых ответов.\n"
            "Источники: карточка ЕГРЮЛ/ЕГРИП, финансовая отчётность (только у юрлиц), "
            "активные арбитражные иски в роли ответчика, исполнительные производства ФССП, "
            "сообщения Федресурса, записи ЕФРСБ.\n"
            "Расходует 5–6 запросов API. На бесплатном тарифе это около 16 проверок "
            "в сутки, поэтому не вызывайте повторно по тому же субъекту: ответы "
            "кэшируются, но кэш живёт ограниченное время.\n"
            "Сигналы считаются по формальным правилам и приводятся с указанием источника. "
            "Вердикт о сделке инструмент не выносит — это ваша задача с учётом контекста "
            "пользователя. Если нужны детали по конкретному блоку, вызывайте отдельный "
            "инструмент: `get_legal_cases`, `get_enforcements` и так далее."
        ),
        schema={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "ОГРН, ОГРНИП или ИНН. Можно передать наименование — тогда субъект "
                        "будет найден поиском, но при нескольких совпадениях инструмент "
                        "попросит уточнить"
                    ),
                },
                "purpose": {
                    "type": "string",
                    "description": "Цель проверки — попадёт в отчёт как контекст",
                },
            },
            "required": ["identifier"],
        },
        pre=_report_pre,
        handler=_reports.due_diligence_report,
    ),
    ToolSpec(
        name="bankruptcy_risk",
        title="Отчёт: риск банкротства",
        description=(
            "Оценка риска банкротства по четырём независимым источникам сигналов: записи "
            "ЕФРСБ, намерения кредиторов обратиться в суд (Федресурс, тип "
            "CreditorIntentionGoToCourt — опережающий сигнал, публикуется до возбуждения "
            "дела), исполнительные производства ФССП и капитал по строке 1300 финансовой "
            "отчётности.\n"
            "Расходует 4–5 запросов API. Отдаёт показатели и сигналы со ссылкой на "
            "источник; вероятность банкротства не рассчитывает и вердикт не выносит."
        ),
        schema={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "ОГРН, ОГРНИП или ИНН проверяемого субъекта",
                },
            },
            "required": ["identifier"],
        },
        pre=_report_pre,
        handler=_reports.bankruptcy_risk,
    ),
]


# Эндпоинты, к которым обращаются каскадные инструменты. Нужны, чтобы тест
# покрытия видел: ни один метод API не остался без инструмента.
HANDLER_ENDPOINTS = frozenset({"/search", "/company", "/entrepreneur", "/person", "/bank"})



# ---------------------------------------------------------------------------
# Клиентские параметры
# ---------------------------------------------------------------------------

# `detail` обрабатывается сервером и в запрос к Checko не уходит: у методов API
# такого параметра нет. Добавляется всем инструментам разом, чтобы его нельзя
# было забыть при появлении нового инструмента.
CLIENT_ONLY_PARAMS = frozenset({"detail"})

_DETAIL_PARAM: dict[str, Any] = {
    "detail": {
        "type": "string",
        "enum": ["compact", "full"],
        "description": (
            "Степень детализации ответа. 'compact' (по умолчанию) сворачивает длинные "
            "списки и оставляет сводные показатели — этого достаточно для оценки риска. "
            "'full' отдаёт ответ API целиком; берите его только когда нужны все записи, "
            "потому что ответ может превысить лимит вывода MCP-клиента и быть обрезанным."
        ),
    }
}

for _spec in TOOLS:
    _spec.schema["properties"].update(_DETAIL_PARAM)


TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}
