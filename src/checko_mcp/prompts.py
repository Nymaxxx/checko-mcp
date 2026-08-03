"""MCP-prompts: готовые сценарии работы с Checko-инструментами.

Каждый prompt — это шаблон с подстановкой аргументов. На выходе — `GetPromptResult`
с одним `PromptMessage(role="user", content=<подставленный текст>)`. Текст содержит
последовательность вызовов инструментов и шаблон финального ответа.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import mcp_types as types

from ._validation import ValidationError, check_format

PromptBuilder = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class PromptSpec:
    name: str
    title: str
    description: str
    arguments: list[types.PromptArgument]
    builder: PromptBuilder = field(repr=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _required(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None or str(value).strip() == "":
        raise ValidationError(f"Отсутствует обязательный аргумент '{key}'.")
    return str(value).strip()


def _opt(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _purpose_block(purpose: str) -> str:
    return f"\nЦель: {purpose}\n" if purpose else ""


def _context_block(context: str) -> str:
    return f"\nКонтекст: {context}\n" if context else ""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _check_counterparty(args: dict[str, Any]) -> str:
    query = _required(args, "query")
    purpose = _opt(args, "purpose")
    purpose_arg = f', purpose="{purpose}"' if purpose else ""
    return f"""\
Проведи комплексную проверку контрагента: {query}.{_purpose_block(purpose)}
Перед началом учти правила из ресурса `checko://docs/agent-guide`.

Порядок работы:

1. Вызови `due_diligence_report(identifier="{query}"{purpose_arg})`. Один вызов сам
   определит вид субъекта и параллельно опросит шесть реестров: ЕГРЮЛ/ЕГРИП,
   финансовую отчётность, активные иски в роли ответчика, исполнительные производства
   ФССП, Федресурс и ЕФРСБ. Вручную по отдельным инструментам это собирать не нужно.
   Если `{query}` — наименование и найдено несколько субъектов, инструмент попросит
   уточнить: спроси пользователя и повтори вызов с конкретным ОГРН или ИНН.
2. Разбери блок `сигналы`: там уже посчитаны формальные признаки риска с указанием
   источника. Проверь `не_удалось_проверить` — если какой-то реестр не ответил,
   об этом надо сказать, а не молчать.
3. Углубляйся только там, где отчёт показал проблему. Например, при непустых иска́х —
   `get_legal_cases(..., sort="-date", detail="full")`; при долгах у приставов —
   `get_enforcements(...)`. Лишние вызовы расходуют платную квоту.

Сформируй структурированное резюме:

- **Общий вывод:** ✅ работать можно / ⚠️ работать с осторожностью / 🚫 не рекомендуется.
  Вывод делаешь ты — инструмент его намеренно не выносит.
- **Базовые факты:** статус, размер (категория МСП), руководитель, ключевые учредители.
- **Финансы:** выручка, прибыль и капитал по годам с динамикой в процентах.
- **Долги и споры:** активные иски (число, сумма, крупнейшие истцы) и исполнительные
  производства (количество и непогашенный остаток).
- **Сигналы рисков:** списком с приоритетом 🔴/🟠/🟡 и ссылкой на конкретное поле или факт.
- **Источники и оговорки:** на каких данных построено заключение, что проверить не удалось,
  какова давность (арбитраж запаздывает на одну-две недели).
"""


def _verify_bank_details(args: dict[str, Any]) -> str:
    inn = _required(args, "inn")
    bic = _required(args, "bic")
    if not (len(inn) == 10 or len(inn) == 12) or not inn.isdigit():
        raise ValidationError("'inn' должен содержать 10 цифр (юрлицо) или 12 цифр (ИП/физлицо).")
    check_format(bic, "bic", 9)
    subject_kind = "org" if len(inn) == 10 else "entrepreneur"
    return f"""\
Проверь корректность платёжных реквизитов перед оплатой:

- ИНН: `{inn}` ({"юрлицо" if len(inn) == 10 else "ИП или физлицо"})
- БИК: `{bic}`

Шаги:

1. `profile(identifier="{inn}", kind="{subject_kind}")` — проверь, что субъект существует
   и его `Статус.Наим == "Действует"`.
2. `get_bank(bic="{bic}")` — проверь, что банк существует и активен.

Ответ дай в виде чеклиста:

- ✅/❌ ИНН валиден и относится к действующему субъекту: <название> (<статус>, <дата статуса>)
- ✅/❌ БИК валиден и принадлежит действующему банку: <название банка>, корсчёт <…>
- Если есть несоответствия (ликвидирован, отозвана лицензия, ИНН не найден) — \
прямо назови конкретные риски и не рекомендуй платёж.
"""


def _assess_bankruptcy_risk(args: dict[str, Any]) -> str:
    inn = _required(args, "inn")
    context = _opt(args, "context")
    if not (len(inn) == 10 or len(inn) == 12) or not inn.isdigit():
        raise ValidationError("'inn' должен содержать 10 (юрлицо) или 12 (ИП/физлицо) цифр.")
    return f"""\
Оцени риск банкротства субъекта с ИНН `{inn}`.{_context_block(context)}
Перед началом учти правила из ресурса `checko://docs/agent-guide`.
Если речь о физлице (ИНН 12 цифр) — подтверди у пользователя законное основание (152-ФЗ, \
см. `checko://docs/legal`).

Шаги:

1. `bankruptcy_risk(identifier="{inn}")` — один вызов проверит четыре независимых источника:
   записи ЕФРСБ, намерения кредиторов обратиться в суд (Федресурс,
   `CreditorIntentionGoToCourt` — опережающий сигнал, публикуется до возбуждения дела),
   исполнительные производства ФССП и капитал по строке 1300.
   Вид субъекта определится по числу цифр в идентификаторе автоматически.
2. Разбери блок `сигналы` и `показатели`. Проверь `не_удалось_проверить`.
3. Дополни картину только если это меняет вывод:
   `get_legal_cases(inn="{inn}", role="defendant", active=true, actual=true)` —
   активные иски-ответчик, их сумма относительно выручки.

Итоговая оценка по шкале:

- 🔴 **Высокий:** открыта процедура банкротства, или зафиксированы намерения кредиторов, \
или капитал глубоко отрицательный, или сумма исков сопоставима с выручкой.
- 🟠 **Повышенный:** множественные активные иски, отрицательная динамика финансов, \
единичные намерения о банкротстве.
- 🟡 **Умеренный:** есть активные иски, но финансы стабильны.
- 🟢 **Низкий:** нет банкротных сигналов, активных крупных исков, финансы здоровые.

Обоснуй оценку конкретными фактами и цифрами из ответов API.
"""


def _audit_person(args: dict[str, Any]) -> str:
    inn = _required(args, "inn")
    purpose = _opt(args, "purpose")
    check_format(inn, "inn", 12)
    return f"""\
Проведи полный аудит физического лица с ИНН `{inn}` по методологии Checko MCP.{_purpose_block(purpose)}
ВАЖНО: персональные данные физлица обрабатываются в соответствии с **152-ФЗ**. \
Перед началом подтверди у пользователя законное основание для аудита \
(см. `checko://docs/legal`). При отсутствии основания — вежливо откажи.

Используй методологию из ресурса `checko://playbooks/audit/methodology` и \
приоритизированный чеклист `checko://playbooks/audit/anomaly-checklist`.

Этапы:

1. **Базовый профиль** — `profile(identifier="{inn}", kind="person")`. Зафиксируй:
   - руководительство (`Руковод[]`),
   - учредительство (`Учред[]`),
   - ИП (`ИП[]`),
   - товарные знаки (`ТоварЗнак[]`),
   - ЕФРСБ (`ЕФРСБ[]`),
   - флаги: `МассРуковод`, `МассУчред`, `Санкции`, `НедобПост`.

2. **По каждой связанной организации** — `profile(identifier=<ОГРН>)`. Особое внимание:
   статус, факторы риска, признаки реальной деятельности (выручка, налоги, лицензии).

3. **По каждому ИП** — `profile(identifier=<ОГРНИП>)`. Статус, виды деятельности, лицензии.

4. **Финансовая глубина** — для крупных или подозрительных компаний: \
`get_finances(ogrn=<ОГРН>, extended=true)`. Динамика выручки, прибыли, капитала.

5. **Хронология** — `get_timeline(inn="{inn}")` для истории изменений (входы/выходы из \
компаний, регистрации/ликвидации ИП).

6. **Банкротные сигналы** — `get_fedresurs(inn="{inn}")` и `get_bankruptcy_messages(inn="{inn}")`.

7. **Сверь с чеклистом аномалий** — `checko://playbooks/audit/anomaly-checklist`.

Результат — структурированный отчёт по шаблону `checko://playbooks/audit/template`. \
Включи: красные флаги (с приоритетом), общий профиль, финансовый периметр, \
оценку рисков и рекомендации.
"""


def _evaluate_tender_participant(args: dict[str, Any]) -> str:
    query = _required(args, "query")
    purpose = _opt(args, "purpose")
    return f"""\
Оцени участника тендера: {query}.{_purpose_block(purpose)}
Цель — обоснованное решение о допуске к тендеру или работе с участником.

Шаги:

1. Если `{query}` — название, сначала `resolve(query="{query}")`.
   Если уже есть ОГРН/ИНН — этот шаг пропусти.
2. `profile(identifier=<ОГРН>)` — статус, руководство, учредители. Особое внимание:
   `НедобПост` (реестр недобросовестных поставщиков ФАС), `МассАдрес`, `МассРуковод`, \
`МассУчред`, размер уставного капитала, давность регистрации.
3. `get_contracts(ogrn=<ОГРН>, law="44")` И `get_contracts(ogrn=<ОГРН>, law="223")` — \
два вызова, объедини результаты на своей стороне:
   - сколько контрактов выполнено,
   - суммы,
   - была ли практика по расторжениям,
   - крупнейшие заказчики.
4. `get_inspections(ogrn=<ОГРН>)` — проверки и нарушения. Зафиксируй типы нарушений и даты.
5. `get_legal_cases(ogrn=<ОГРН>, role="defendant", actual=true)` — иски о неисполнении \
обязательств, штрафах, взыскании по контрактам.
6. `get_finances(ogrn=<ОГРН>, extended=true)` — последние 3 года: размер бизнеса \
(стр. 1600), выручка (2110), способность исполнить контракт нужного объёма.

Резюме:

- **Допуск:** ✅ можно / ⚠️ с оговорками / 🚫 не рекомендуется.
- **Опыт:** число и сумма выполненных госконтрактов, ключевые заказчики.
- **Дисциплина:** наличие в РНП, иски о расторжении, штрафы.
- **Способность выполнить:** сравнение масштаба бизнеса с предполагаемым объёмом контракта.
- **Риски:** перечисли с приоритетом (🔴/🟠/🟡) и конкретными ссылками на факты.
"""


def _analyze_finances(args: dict[str, Any]) -> str:
    identifier = _required(args, "ogrn_or_inn")
    years_raw = _opt(args, "years")
    years = years_raw if years_raw else "5"
    if identifier.isdigit() and len(identifier) == 13:
        param = f'ogrn="{identifier}"'
    elif identifier.isdigit() and len(identifier) == 10:
        param = f'inn="{identifier}"'
    else:
        raise ValidationError(
            "'ogrn_or_inn' должен быть ОГРН (13 цифр) или ИНН юрлица (10 цифр)."
        )
    return f"""\
Проанализируй финансовую динамику организации `{identifier}` за последние {years} лет.

Шаги:

1. `get_finances({param}, extended=true)` — расширенная отчётность по строкам.
2. По массиву `Фин[]` собери динамику ключевых строк:
   - **2110 (выручка)** — рост / падение год к году в %.
   - **2400 (чистая прибыль / убыток)** — знак, динамика, маржинальность \
(прибыль / выручка).
   - **1300 (капитал и резервы)** — знак (отрицательный → формальные признаки банкротства), \
динамика.
   - **1400 + 1500 (обязательства)** — общая долговая нагрузка, отношение к капиталу.
   - **1600 (баланс активов)** — масштаб бизнеса.

3. Найди аномалии:
   - резкие скачки выручки (>50% год к году в любую сторону),
   - переход прибыли в убыток или наоборот,
   - отрицательный или близкий к нулю капитал,
   - быстрый рост обязательств без соответствующего роста активов,
   - отсутствующие периоды (пропуск отчётности).

Резюме:

- **Динамика выручки:** в формате таблицы или списка по годам.
- **Прибыльность:** маржа и тренд.
- **Финансовая устойчивость:** капитал и долговая нагрузка.
- **Аномалии:** перечисли с конкретными цифрами.
- **Замечание:** последний завершённый год может отсутствовать — ГИР БО публикует с задержкой ~6 мес.
"""


# ---------------------------------------------------------------------------
# Prompts registry
# ---------------------------------------------------------------------------

PROMPTS: list[PromptSpec] = [
    PromptSpec(
        name="check_counterparty",
        title="Проверка контрагента",
        description=(
            "Комплексная due-diligence проверка контрагента перед сделкой "
            "(статус, финансы, иски, банкротные сигналы)."
        ),
        arguments=[
            types.PromptArgument(
                name="query",
                description="Название, ИНН или ОГРН организации",
                required=True,
            ),
            types.PromptArgument(
                name="purpose",
                description="Цель проверки (например, 'договор поставки на 5 млн')",
                required=False,
            ),
        ],
        builder=_check_counterparty,
    ),
    PromptSpec(
        name="verify_bank_details",
        title="Проверка платёжных реквизитов",
        description="Проверка ИНН и БИК перед оплатой счёта.",
        arguments=[
            types.PromptArgument(
                name="inn",
                description="ИНН плательщика/получателя (10 цифр для юрлица, 12 — для ИП/физлица)",
                required=True,
            ),
            types.PromptArgument(
                name="bic",
                description="БИК банка (9 цифр)",
                required=True,
            ),
        ],
        builder=_verify_bank_details,
    ),
    PromptSpec(
        name="assess_bankruptcy_risk",
        title="Оценка риска банкротства",
        description=(
            "Оценка вероятности банкротства организации, ИП или физлица "
            "по Федресурсу, ЕФРСБ, искам и финансам."
        ),
        arguments=[
            types.PromptArgument(
                name="inn",
                description="ИНН субъекта (10 цифр для юрлица, 12 — для ИП/физлица)",
                required=True,
            ),
            types.PromptArgument(
                name="context",
                description="Контекст оценки (например, 'дебитор не платит 4 месяца')",
                required=False,
            ),
        ],
        builder=_assess_bankruptcy_risk,
    ),
    PromptSpec(
        name="audit_person",
        title="Аудит физлица",
        description=(
            "Полный аудит физического лица по методологии Checko MCP "
            "(playbooks/audit). Требует законного основания (152-ФЗ)."
        ),
        arguments=[
            types.PromptArgument(
                name="inn",
                description="ИНН физического лица (12 цифр)",
                required=True,
            ),
            types.PromptArgument(
                name="purpose",
                description="Цель аудита",
                required=False,
            ),
        ],
        builder=_audit_person,
    ),
    PromptSpec(
        name="evaluate_tender_participant",
        title="Оценка участника тендера",
        description=(
            "Оценка организации как участника тендера: история госконтрактов, "
            "проверки, иски, способность выполнить."
        ),
        arguments=[
            types.PromptArgument(
                name="query",
                description="Название, ИНН или ОГРН организации-участника",
                required=True,
            ),
            types.PromptArgument(
                name="purpose",
                description="Описание тендера / цель оценки",
                required=False,
            ),
        ],
        builder=_evaluate_tender_participant,
    ),
    PromptSpec(
        name="analyze_finances",
        title="Анализ финансовой динамики",
        description="Анализ выручки, прибыли, капитала и долгов организации за несколько лет.",
        arguments=[
            types.PromptArgument(
                name="ogrn_or_inn",
                description="ОГРН (13 цифр) или ИНН юрлица (10 цифр)",
                required=True,
            ),
            types.PromptArgument(
                name="years",
                description="Сколько последних лет анализировать (по умолчанию 5)",
                required=False,
            ),
        ],
        builder=_analyze_finances,
    ),
]


PROMPTS_BY_NAME: dict[str, PromptSpec] = {p.name: p for p in PROMPTS}


def list_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name=spec.name,
            title=spec.title,
            description=spec.description,
            arguments=spec.arguments,
        )
        for spec in PROMPTS
    ]


def get_prompt(name: str, arguments: dict[str, Any] | None) -> types.GetPromptResult:
    spec = PROMPTS_BY_NAME.get(name)
    if spec is None:
        raise ValidationError(f"Неизвестный prompt: {name}")
    text = spec.builder(arguments or {})
    return types.GetPromptResult(
        description=spec.description,
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=text),
            )
        ],
    )
