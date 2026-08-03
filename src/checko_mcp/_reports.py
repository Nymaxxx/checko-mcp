"""Каскадные инструменты: один вызов агента — несколько запросов к API.

Зачем каскад. Проверка контрагента — это шесть обращений к разным реестрам,
и агент собирал их вручную: сам решал, какой метод вызвать по числу цифр в ИНН,
сам держал в контексте шесть сырых ответов, сам не забывал про исполнительные
производства. Каждый шаг — место для ошибки и лишний расход контекста.

Здесь последовательность зашита в код: маршрутизация детерминированная, запросы
идут параллельно, наружу отдаётся сводка с уже посчитанными сигналами.

Что каскад НЕ делает: не выносит вердикт. Сигналы считаются по явным правилам
и приводятся со ссылкой на источник, а решение — за пользователем и агентом.
Правила проверяемы, суждение о сделке — нет.
"""

import asyncio
from typing import Any

from . import _routing
from ._shape import COMPACT, FINANCE_KEY_LINES, shape
from ._validation import ValidationError

CRITICAL = "🔴 критично"
IMPORTANT = "🟠 важно"
NOTICE = "🟡 внимание"

DISCLAIMER = (
    "Сигналы рассчитаны по формальным правилам на основании данных реестров. "
    "Это не вывод о добросовестности и не рекомендация по сделке: проверьте "
    "ключевые факты в первоисточниках."
)

# Поля, по которым отдаётся короткая карточка кандидата в `resolve`.
_CANDIDATE_FIELDS = (
    "ОГРН", "ОГРНИП", "ИНН", "КПП", "НаимСокр", "НаимПолн", "ФИО",
    "ДатаРег", "Статус", "РегионКод", "ЮрАдрес", "ОКВЭД",
)

RESOLVE_DEFAULT_LIMIT = 10


def _is_empty(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    if data is None:
        return True
    if isinstance(data, (dict, list, str)):
        return len(data) == 0
    return False


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _project(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    result: dict[str, Any] = {}
    for field in _CANDIDATE_FIELDS:
        if field in record:
            value = record[field]
            if isinstance(value, dict):
                value = value.get("Наим") or value.get("Код") or value
            result[field] = value
    return result


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------

async def profile(client, args: dict[str, Any], detail: str) -> dict[str, Any]:
    identifier = args.get("identifier")
    if not identifier:
        raise ValidationError("Параметр 'identifier' обязателен.")

    kind = args.get("kind")
    route = _routing.route_for_kind(identifier, kind) if kind else _routing.classify(identifier)

    params = dict(route.params)
    if args.get("source"):
        params["source"] = "true"

    payload = await client.get(route.endpoint, **params)
    used = route

    if _is_empty(payload) and route.fallback is not None:
        fallback_payload = await client.get(route.fallback.endpoint, **route.fallback.params)
        if not _is_empty(fallback_payload):
            payload, used = fallback_payload, route.fallback

    result = dict(shape(used.endpoint, payload, detail))
    result["субъект"] = {
        "вид": used.kind,
        "метод_api": used.endpoint,
        "искали_по": ", ".join(sorted(used.params)),
    }

    notes: list[str] = []
    if route.note:
        notes.append(route.note)
    if _is_empty(payload):
        notes.append(
            "Ответ пустой. Проверьте идентификатор: пустой ответ Checko отдаёт и на "
            "заведомо неподдерживаемые данные, например на белорусский УНП."
        )
    if notes:
        result["субъект"]["примечания"] = notes

    return result


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

async def resolve(client, args: dict[str, Any], detail: str) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValidationError("Параметр 'query' обязателен.")

    limit = int(args.get("limit") or RESOLVE_DEFAULT_LIMIT)
    digits = _routing.normalize(query)

    # Идентификатор — маршрутизируем сразу, поиск не нужен.
    if digits.isdigit():
        route = _routing.classify(digits)
        payload = await client.get(route.endpoint, **route.params)
        used = route
        if _is_empty(payload) and route.fallback is not None:
            alternative = await client.get(route.fallback.endpoint, **route.fallback.params)
            if not _is_empty(alternative):
                payload, used = alternative, route.fallback

        found = _project(payload.get("data") or {})
        return {
            "запрос": query,
            "распознано_как": used.kind,
            "метод_api": used.endpoint,
            "найдено": 1 if found else 0,
            "кандидаты": [found] if found else [],
            "meta": payload.get("meta"),
        }

    by = str(args.get("by") or "name")
    obj = str(args.get("obj") or "org")
    params: dict[str, Any] = {"by": by, "obj": obj, "query": query}
    for optional in ("region", "okved", "opf"):
        if args.get(optional):
            params[optional] = args[optional]
    if args.get("active"):
        params["active"] = "true"

    payload = await client.get("/search", **params)

    # detail="full" отдаёт ответ поиска целиком, без проекции полей.
    if detail != COMPACT:
        return shape("/search", payload, detail)

    data = payload.get("data") or {}
    records = data.get("Записи") or []
    candidates = [_project(record) for record in records[:limit]]

    result: dict[str, Any] = {
        "запрос": query,
        "искали": {"by": by, "obj": obj},
        "найдено_всего": data.get("ЗапВсего", len(records)),
        "показано": len(candidates),
        "кандидаты": candidates,
        "meta": payload.get("meta"),
    }
    if data.get("ЗапВсего", 0) > len(candidates):
        result["примечание"] = (
            "Показаны только первые кандидаты. Уточните запрос параметрами region, okved, "
            "opf или active=true, увеличьте limit — либо запросите detail=\"full\", "
            "чтобы получить ответ поиска целиком."
        )
    return result


# ---------------------------------------------------------------------------
# Сигналы
# ---------------------------------------------------------------------------

def _signal(level: str, fact: str, source: str) -> dict[str, str]:
    return {"уровень": level, "факт": fact, "источник": source}


def _company_signals(data: dict[str, Any]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    status = (data.get("Статус") or {})
    status_name = status.get("Наим") if isinstance(status, dict) else status
    if status_name and status_name != "Действует":
        signals.append(_signal(CRITICAL, f"Статус: {status_name}", "ЕГРЮЛ/ЕГРИП"))

    flags = (
        ("Санкции", CRITICAL, "Включён в санкционные списки"),
        ("НелегалФин", CRITICAL, "Признаки нелегальной финансовой деятельности (ЦБ РФ)"),
        ("ДисквЛица", CRITICAL, "Есть дисквалифицированные лица"),
        ("НедобПост", IMPORTANT, "В реестре недобросовестных поставщиков (ФАС)"),
        ("СанкцУчр", IMPORTANT, "Учредитель под санкциями"),
        ("МассРуковод", NOTICE, "Руководитель числится массовым"),
        ("МассУчред", NOTICE, "Учредитель числится массовым"),
    )
    for key, level, text in flags:
        if data.get(key) is True:
            signals.append(_signal(level, text, f"поле {key}"))

    if data.get("ЕФРСБ"):
        signals.append(
            _signal(CRITICAL, "Есть записи ЕФРСБ в карточке организации", "поле ЕФРСБ")
        )

    address = data.get("ЮрАдрес") or {}
    if isinstance(address, dict):
        if address.get("Недост"):
            signals.append(_signal(IMPORTANT, "Адрес признан недостоверным", "ЮрАдрес.Недост"))
        if address.get("МассАдрес"):
            signals.append(_signal(NOTICE, "Адрес массовой регистрации", "ЮрАдрес.МассАдрес"))

    for manager in data.get("Руковод") or []:
        if not isinstance(manager, dict):
            continue
        if manager.get("ДисквЛицо"):
            signals.append(
                _signal(CRITICAL, "Руководитель дисквалифицирован", "Руковод[].ДисквЛицо")
            )
        if manager.get("Недост"):
            signals.append(
                _signal(IMPORTANT, "Сведения о руководителе недостоверны", "Руковод[].Недост")
            )
    return signals


def _finance_summary(data: Any) -> dict[str, Any]:
    """Ключевые строки по годам плюс сигнал по отрицательному капиталу."""
    if not isinstance(data, dict) or not data:
        return {}

    years = sorted(k for k in data if str(k).isdigit())
    series: dict[str, dict[str, Any]] = {}
    for code in ("2110", "2400", "1300", "1600"):
        row = {}
        for year in years:
            line = (data.get(year) or {}).get(code)
            if isinstance(line, dict):
                value = _num(line.get("СумОтч"))
                if value is not None:
                    row[year] = value
        if row:
            series[f"{code} — {FINANCE_KEY_LINES.get(code, code)}"] = row
    return {"годы": years, "показатели": series} if series else {}


def _finance_signals(summary: dict[str, Any]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for label, row in (summary.get("показатели") or {}).items():
        if not label.startswith("1300") or not row:
            continue
        last_year = max(row)
        if row[last_year] < 0:
            signals.append(
                _signal(
                    IMPORTANT,
                    f"Капитал отрицательный за {last_year}: {row[last_year]:,.0f} руб.".replace(
                        ",", " "
                    ),
                    "строка 1300",
                )
            )
    return signals


def _records_summary(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {"записей": len(data) if isinstance(data, list) else 0}
    summary = {key: data[key] for key in keys if key in data}
    summary.setdefault("записей", data.get("ЗапВсего", 0))
    return summary


def _top_plaintiffs(payload: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for record in (payload.get("data") or {}).get("Записи") or []:
        amount = _num(record.get("СуммИск")) or 0.0
        for party in record.get("Ист") or []:
            if isinstance(party, dict) and party.get("Наим"):
                totals[party["Наим"]] = totals.get(party["Наим"], 0.0) + amount
    ranked = sorted(totals.items(), key=lambda item: -item[1])[:limit]
    return [{"истец": name, "сумма_исков": amount} for name, amount in ranked]


# ---------------------------------------------------------------------------
# Каскадные отчёты
# ---------------------------------------------------------------------------

async def _gather(client, requests: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Параллельно выполнить запросы; сбой одного не роняет отчёт."""

    async def run(endpoint: str, params: dict[str, Any]):
        return await client.get(endpoint, **params)

    names = list(requests)
    results = await asyncio.gather(
        *(run(*requests[name]) for name in names), return_exceptions=True
    )
    return dict(zip(names, results, strict=True))


async def _identify(client, args: dict[str, Any]) -> tuple[str, _routing.Route]:
    """Получить идентификатор: цифры берём как есть, текст разрешаем через поиск."""
    raw = str(args.get("identifier") or args.get("query") or "").strip()
    if not raw:
        raise ValidationError("Укажите 'identifier' — ОГРН, ОГРНИП или ИНН.")

    digits = _routing.normalize(raw)
    if digits.isdigit():
        return digits, _routing.classify(digits)

    found = await resolve(client, {"query": raw, "limit": 5}, COMPACT)
    candidates = found.get("кандидаты") or []
    if not candidates:
        raise ValidationError(f"По запросу «{raw}» ничего не найдено — уточните наименование.")
    if len(candidates) > 1:
        names = "; ".join(
            f"{c.get('НаимСокр') or c.get('ФИО')} (ИНН {c.get('ИНН')})" for c in candidates
        )
        raise ValidationError(
            f"По запросу «{raw}» найдено несколько субъектов — уточните, какой проверять, "
            f"и передайте его ОГРН или ИНН: {names}"
        )
    identifier = candidates[0].get("ОГРН") or candidates[0].get("ИНН") or ""
    return identifier, _routing.classify(_routing.normalize(identifier))


async def due_diligence_report(client, args: dict[str, Any], detail: str) -> dict[str, Any]:
    identifier, route = await _identify(client, args)
    before = client.billed_requests

    if route.kind == _routing.BANK:
        raise ValidationError(
            "9 цифр распознаны как БИК банка. Для банка используйте инструмент `get_bank`."
        )

    subject = _routing.subject_params(identifier)
    plan: dict[str, tuple[str, dict[str, Any]]] = {
        "карточка": (route.endpoint, route.params),
        "иски": (
            "/legal-cases",
            {**subject, "role": "defendant", "actual": "true", "active": "true", "sort": "-date"},
        ),
        "исполнительные_производства": ("/enforcements", dict(subject)),
        "федресурс": ("/fedresurs", {**subject, "sort": "-date"}),
        "банкротство": ("/bankruptcy-messages", {**subject, "sort": "-date"}),
    }
    if route.kind == _routing.ORG:
        plan["финансы"] = ("/finances", {**subject, "extended": "true"})

    fetched = await _gather(client, plan)

    unavailable: list[str] = []
    signals: list[dict[str, str]] = []
    report: dict[str, Any] = {
        "проверенный_субъект": {"идентификатор": identifier, "вид": route.kind}
    }

    card = fetched.get("карточка")
    if isinstance(card, Exception):
        unavailable.append(f"карточка субъекта: {card}")
    else:
        data = card.get("data") or {}
        report["проверенный_субъект"].update(_project(data))
        managers = data.get("Руковод") or []
        if managers and isinstance(managers[0], dict):
            report["проверенный_субъект"]["руководитель"] = managers[0].get("ФИО")
        signals += _company_signals(data)

    finances = fetched.get("финансы")
    if isinstance(finances, Exception):
        unavailable.append(f"финансовая отчётность: {finances}")
    elif finances is not None:
        summary = _finance_summary(finances.get("data"))
        report["финансы"] = summary or {"нет данных": "отчётность не публиковалась"}
        signals += _finance_signals(summary)
    elif route.kind != _routing.ORG:
        report["финансы"] = {"нет данных": "отчётность сдают только юридические лица"}

    cases = fetched.get("иски")
    if isinstance(cases, Exception):
        unavailable.append(f"арбитражные дела: {cases}")
    else:
        summary = _records_summary(cases, ("ЗапВсего", "ОбщСуммИск"))
        summary["крупнейшие_истцы"] = _top_plaintiffs(cases)
        report["активные_иски_как_ответчик"] = summary
        if summary.get("записей"):
            amount = _num(summary.get("ОбщСуммИск")) or 0.0
            signals.append(
                _signal(
                    IMPORTANT,
                    f"Активных исков как ответчик: {summary['записей']}, "
                    f"общая сумма {amount:,.0f} руб.".replace(",", " "),
                    "Картотека арбитражных дел",
                )
            )

    enforcements = fetched.get("исполнительные_производства")
    if isinstance(enforcements, Exception):
        unavailable.append(f"исполнительные производства: {enforcements}")
    else:
        summary = _records_summary(enforcements, ("ОбщКолич", "ОбщСум", "ОстЗадолж"))
        report["исполнительные_производства"] = summary
        outstanding = _num(summary.get("ОстЗадолж")) or 0.0
        if outstanding > 0:
            signals.append(
                _signal(
                    IMPORTANT,
                    f"Непогашенный остаток по исполнительным производствам: "
                    f"{outstanding:,.0f} руб. ({summary.get('ОбщКолич')} производств)".replace(
                        ",", " "
                    ),
                    "ФССП",
                )
            )

    fedresurs = fetched.get("федресурс")
    if isinstance(fedresurs, Exception):
        unavailable.append(f"Федресурс: {fedresurs}")
    else:
        records = (fedresurs.get("data") or {}).get("Записи") or []
        intentions = [r for r in records if r.get("Тип") == "CreditorIntentionGoToCourt"]
        report["федресурс"] = {
            "записей": (fedresurs.get("data") or {}).get("ЗапВсего", len(records)),
            "намерений_о_банкротстве": len(intentions),
        }
        if intentions:
            signals.append(
                _signal(
                    CRITICAL,
                    f"Кредиторы заявили о намерении подать на банкротство: {len(intentions)}",
                    "Федресурс, CreditorIntentionGoToCourt",
                )
            )

    bankruptcy = fetched.get("банкротство")
    if isinstance(bankruptcy, Exception):
        unavailable.append(f"ЕФРСБ: {bankruptcy}")
    else:
        total = (bankruptcy.get("data") or {}).get("ЗапВсего", 0)
        report["ефрсб"] = {"записей": total}
        if total:
            signals.append(
                _signal(CRITICAL, f"Записей в реестре банкротств: {total}", "ЕФРСБ")
            )

    order = {CRITICAL: 0, IMPORTANT: 1, NOTICE: 2}
    report["сигналы"] = sorted(signals, key=lambda s: order.get(s["уровень"], 9))
    report["сигналов_не_найдено"] = not signals
    if unavailable:
        report["не_удалось_проверить"] = unavailable
    if args.get("purpose"):
        report["цель_проверки"] = args["purpose"]
    report["запросов_в_api"] = client.billed_requests - before
    report["оговорка"] = DISCLAIMER
    return report


async def bankruptcy_risk(client, args: dict[str, Any], detail: str) -> dict[str, Any]:
    identifier, route = await _identify(client, args)
    before = client.billed_requests

    subject = _routing.subject_params(identifier)
    plan: dict[str, tuple[str, dict[str, Any]]] = {
        "карточка": (route.endpoint, route.params),
        "федресурс": ("/fedresurs", {**subject, "type": "CreditorIntentionGoToCourt"}),
        "ефрсб": ("/bankruptcy-messages", {**subject, "sort": "-date"}),
        "исполнительные_производства": ("/enforcements", dict(subject)),
    }
    if route.kind == _routing.ORG:
        plan["финансы"] = ("/finances", {**subject, "extended": "true"})

    fetched = await _gather(client, plan)
    signals: list[dict[str, str]] = []
    sources: dict[str, Any] = {}
    unavailable: list[str] = []

    card = fetched.get("карточка")
    if isinstance(card, Exception):
        unavailable.append(f"карточка субъекта: {card}")
        subject_card: dict[str, Any] = {}
    else:
        subject_card = card.get("data") or {}
        signals += [
            s
            for s in _company_signals(subject_card)
            if s["уровень"] == CRITICAL or "ЕФРСБ" in s["источник"]
        ]

    ефрсб = fetched.get("ефрсб")
    if isinstance(ефрсб, Exception):
        unavailable.append(f"ЕФРСБ: {ефрсб}")
    else:
        total = (ефрсб.get("data") or {}).get("ЗапВсего", 0)
        sources["ефрсб_записей"] = total
        if total:
            signals.append(
                _signal(
                    CRITICAL,
                    f"Открыта или завершена процедура банкротства: {total} записей",
                    "ЕФРСБ",
                )
            )

    fedresurs = fetched.get("федресурс")
    if isinstance(fedresurs, Exception):
        unavailable.append(f"Федресурс: {fedresurs}")
    else:
        total = (fedresurs.get("data") or {}).get("ЗапВсего", 0)
        sources["намерений_о_банкротстве"] = total
        if total:
            signals.append(
                _signal(
                    CRITICAL,
                    f"Намерений кредиторов обратиться в суд: {total}. Это опережающий "
                    "сигнал — публикуется до возбуждения дела",
                    "Федресурс, CreditorIntentionGoToCourt",
                )
            )

    enforcements = fetched.get("исполнительные_производства")
    if isinstance(enforcements, Exception):
        unavailable.append(f"исполнительные производства: {enforcements}")
    else:
        summary = _records_summary(enforcements, ("ОбщКолич", "ОбщСум", "ОстЗадолж"))
        sources["исполнительные_производства"] = summary
        outstanding = _num(summary.get("ОстЗадолж")) or 0.0
        if outstanding > 0:
            signals.append(
                _signal(
                    IMPORTANT,
                    f"Долги на взыскании у приставов: остаток {outstanding:,.0f} руб.".replace(
                        ",", " "
                    ),
                    "ФССП",
                )
            )

    finances = fetched.get("финансы")
    if isinstance(finances, Exception):
        unavailable.append(f"финансовая отчётность: {finances}")
    elif finances is not None:
        summary = _finance_summary(finances.get("data"))
        sources["финансы"] = summary or {"нет данных": "отчётность не публиковалась"}
        signals += _finance_signals(summary)

    order = {CRITICAL: 0, IMPORTANT: 1, NOTICE: 2}
    signals.sort(key=lambda s: order.get(s["уровень"], 9))

    return {
        "проверенный_субъект": {
            "идентификатор": identifier,
            "вид": route.kind,
            **_project(subject_card),
        },
        "проверенные_источники": [
            "ЕФРСБ — реестр банкротств",
            "Федресурс — намерения кредиторов",
            "ФССП — исполнительные производства",
            "ГИР БО — капитал по строке 1300"
            if route.kind == _routing.ORG
            else "финансовая отчётность у ИП отсутствует",
        ],
        "показатели": sources,
        "сигналы": signals,
        "сигналов_не_найдено": not signals,
        **({"не_удалось_проверить": unavailable} if unavailable else {}),
        "запросов_в_api": client.billed_requests - before,
        "оговорка": DISCLAIMER,
    }


__all__ = ["bankruptcy_risk", "due_diligence_report", "profile", "resolve"]
