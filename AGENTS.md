# AGENTS.md — Руководство для AI-агентов и разработчиков

Этот файл описывает структуру проекта, соглашения по коду и инструкции для AI-агентов, работающих над этим репозиторием.

---

## Обзор проекта

**checko-mcp** — Python MCP-сервер для [Checko.ru API v2](https://checko.ru/integration/api).
Предоставляет AI-ассистентам и MCP-клиентам:

- **13 инструментов** (tools) — каскадная модель: вход (`resolve`, `profile`), готовые отчёты
  (`due_diligence_report`, `bankruptcy_risk`) и девять обёрток над отдельными методами API.
- **6 готовых сценариев** (prompts) — типовые workflow с зашитой последовательностью вызовов.
- **5 справочных ресурсов** (resources) — agent guide, правовая справка, методология аудита.

**Стек:**
- Python 3.11+ (CI: 3.11/3.12/3.13/3.14)
- `mcp>=2,<3` — Python MCP SDK 2.x (stdio-транспорт)
- `httpx2` — async HTTP-клиент (один экземпляр на жизнь сервера)
- `python-dotenv` — загрузка переменных окружения
- `pytest` + `pytest-asyncio` — тесты
- `ruff` — линтер
- Docker / docker-compose — контейнеризация (приоритетный способ запуска)

---

## Структура репозитория

```
checko-mcp/
├── src/
│   └── checko_mcp/
│       ├── __init__.py        — версия пакета
│       ├── __main__.py        — точка входа: asyncio.run(run())
│       ├── _validation.py     — require_any, check_format, coerce_bool, ValidationError
│       ├── _routing.py        — определение вида субъекта по числу цифр идентификатора
│       ├── _shape.py          — сжатие ответа (detail=compact|full)
│       ├── _reports.py        — каскады: resolve, profile, отчёты, расчёт сигналов
│       ├── _cache.py          — TTL-кэш ответов API
│       ├── client.py          — CheckoClient (httpx2.AsyncClient + повторы + кэш)
│       ├── tools.py           — реестр TOOLS: ToolSpec(endpoint | handler, schema, pre)
│       ├── resources.py       — реестр RESOURCES + загрузка markdown (package data + dev fallback)
│       ├── prompts.py         — реестр PROMPTS: 6 готовых сценариев
│       ├── server.py          — MCP Server: list_tools/call_tool, list_resources/read_resource,
│       │                         list_prompts/get_prompt, run
│       └── _resources/        — package data: канонические markdown-файлы (force-include в wheel)
├── tests/
│   ├── conftest.py            — фикстуры: подмена API-ключа, фабрика клиента с MockTransport
│   ├── test_validation.py     — валидаторы
│   ├── test_client.py         — HTTP-клиент (httpx.MockTransport)
│   ├── test_tools.py          — реестр инструментов и pre-валидаторы
│   ├── test_resources.py      — реестр ресурсов и загрузка markdown
│   └── test_prompts.py        — реестр promptов и шаблоны
├── docs/
│   ├── api/                   — справочник по эндпоинтам Checko API
│   │   ├── README.md
│   │   ├── search.md, company.md, entrepreneur.md, person.md
│   │   ├── finances.md, legal-cases.md, contracts.md, inspections.md
│   │   ├── bank.md, timeline.md, fedresurs.md, bankruptcy-messages.md
│   └── instructions/
│       └── agent-guide.md     — каноничный текст ресурса checko://docs/agent-guide
├── playbooks/
│   ├── README.md
│   └── audit/                 — методология/чеклист/шаблон (= ресурсы checko://playbooks/audit/*)
├── .github/
│   ├── workflows/ci.yml       — lint + tests на 4 версиях Python + docker build
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── Dockerfile                 — multi-stage, python:3.13-slim
├── docker-compose.yml         — приоритетный способ запуска (env_file: .env)
├── pyproject.toml             — hatchling, ruff, pytest, [project.optional-dependencies] dev
├── .env.example
├── README.md                  — пользовательская документация
├── AGENTS.md                  — этот файл
├── CHANGELOG.md               — Keep a Changelog + SemVer
├── CONTRIBUTING.md            — как внести вклад
├── SECURITY.md                — политика приёма уязвимостей
├── LEGAL.md                   — правовые основания (152-ФЗ, 149-ФЗ)
└── LICENSE                    — MIT
```

---

## Архитектура

```
AI-клиент (любой MCP-host)
        │ MCP (stdio)
        ▼
server.py
        │  ┌── tools  ─────  list_tools / call_tool      ──▶ tools.py (TOOLS_BY_NAME)
        │  ├── resources ──  list_resources / read_resource ──▶ resources.py
        │  └── prompts  ──   list_prompts / get_prompt       ──▶ prompts.py
        │
        │  call_tool: spec.pre(args) → CheckoClient.get(endpoint, **args)
        ▼
client.py (один httpx.AsyncClient)
        │ HTTPS
        ▼
api.checko.ru/v2/{endpoint}
```

**Поток данных для tool-вызова:**

1. MCP-клиент вызывает инструмент с аргументами.
2. `call_tool()` находит `ToolSpec` в `TOOLS_BY_NAME`.
3. `spec.pre(arguments)` валидирует и нормализует аргументы (raises `ValidationError`).
4. `CheckoClient.get()` делает GET-запрос с автодобавлением `key`.
5. Ответ возвращается как pretty-printed JSON через `TextContent`.
6. Ошибки (`ValidationError`, `CheckoAPIError`) превращаются в `Ошибка: ...`.

**Поток для prompts:**

1. Клиент вызывает `prompts/get` с именем и аргументами.
2. `prompts.get_prompt()` находит `PromptSpec`, валидирует args, выполняет `builder(args)` — возвращает текст.
3. `GetPromptResult` с одним `PromptMessage(role="user", content=<текст>)` отдаётся клиенту.
4. AI-агент получает готовый план действий с уже подставленными параметрами.

**Поток для resources:**

1. Клиент вызывает `resources/list` или `resources/read`.
2. `resources.read_resource_text(uri)` сначала пробует package data (`importlib.resources`), затем падает в dev-fallback на путь в репозитории.
3. Для production wheel канонические `.md`-файлы упакованы через `[tool.hatch.build.targets.wheel.force-include]`.

---

## Соглашения по коду

### Общее

- Язык кода: Python. Комментариев минимум — только то, что код сам по себе не показывает.
- Сообщения об ошибках, описания инструментов и docstrings — на русском (это локализованный инструмент).
- Типизация обязательна (`from typing import Any`, `dict[str, Any]`, `Callable`).
- Форматирование: PEP 8, `ruff` с line-length 100. Длинные cyrillic-описания в `tools.py` исключены из E501 через `per-file-ignores`.
- Импорты сортируются `ruff --fix` (правило `I`).

### Идентификаторы и персональные данные в репозитории

**Правило**: в коде, тестах, документации и примерах — **только синтетические идентификаторы**. Не вносим в репозиторий настоящие ИНН, ОГРН, ОГРНИП, КПП, ОКПО, БИК, паспортные данные, ФИО реальных людей, адреса, телефоны.

- Юрлицо: `1234567890` (ИНН-10), `1234567890123` (ОГРН-13), `123456789` (КПП-9), `01234567` (ОКПО-8).
- ИП/физлицо: `123456789012` (ИНН-12), `123456789012345` (ОГРНИП-15).
- Банк: `123456789` (БИК-9). Реальный БИК для smoke-теста подключается через переменную окружения `SMOKE_TEST_BIC`, **не зашивается в код**.
- Имена: `Иванов Иван Иванович` (универсальный placeholder), названия компаний — `ООО «Тестовая Компания»`, `ООО «Тестовый Поставщик»`.

В примерах ответов API в `docs/api/*.md` идентификаторы маскируются заглушками вида `XXXXXXXXXX`, либо указываются формально валидные синтетические значения. При необходимости показать реальный публичный API-ответ — берите его в локальном `.env` через `SMOKE_TEST_BIC` и т. п., но не коммитьте.

Правило проверяется автоматически: `tests/test_repo_hygiene.py` обходит весь репозиторий и падает на любой закавыченной последовательности из 8–15 цифр вне набора выше. Денежные суммы в примерах ответов идут числами без кавычек и под проверку не попадают. Новое синтетическое значение сначала добавляется в `ALLOWED` этого теста — и только заведомо ничему не принадлежащее.

### `_validation.py`

- Чистый модуль без зависимостей кроме `typing`.
- Все валидаторы поднимают `ValidationError`.
- `require_any(args, *keys)` — хотя бы один ключ должен быть истинным.
- `check_format(value, name, digits)` — `None` пропускается, иначе проверяется длина и `isdigit`.
- `coerce_bool(args, *keys)` — мутирует `args` на месте, конвертируя `True/False` в `"true"/None`.

### `client.py`

- `CheckoClient` — единственный публичный класс.
- `__init__` принимает опциональный `transport: httpx.AsyncBaseTransport` для тестов.
- `get(endpoint, **params)` — единственная точка выхода в сеть.
- Параметры `None` фильтруются перед отправкой.
- При `meta.status == "error"` поднимает `CheckoAPIError(meta.message)`.
- `httpx.AsyncClient` создаётся один раз в `__init__`, закрывается через `aclose()`.
- Таймаут: переменная `CHECKO_TIMEOUT` (по умолчанию 30 сек).

### `tools.py`

- `ToolSpec` — frozen dataclass: `name`, `endpoint`, `description`, `schema`, `pre`.
- Все инструменты собраны в список `TOOLS`, индекс — `TOOLS_BY_NAME`.
- Pre-валидаторы — приватные функции `_xxx_pre(args)`.
- Общие фрагменты схем (пагинация `_PAGE`, диапазон дат `_DATE_RANGE`, сортировка `_SORT_DATE`) вынесены в константы.
- Булевы параметры (`source`, `extended`, `actual`, `active`) конвертируются в строку `"true"` через `coerce_bool`.

### `resources.py`

- `RESOURCES` — список `ResourceSpec(uri, name, title, description, file_name, repo_path)`.
- `read_resource_text(uri)` — сначала пробует `importlib.resources.files("checko_mcp._resources")`,
  при отсутствии (editable / dev) — fallback на `Path(__file__).parents[2] / spec.repo_path`.
- Канонические markdown-файлы остаются в `docs/instructions/`, `playbooks/audit/`, `LEGAL.md` —
  при сборке wheel hatchling копирует их в `checko_mcp/_resources/`.
- Чтобы добавить новый ресурс: добавить `ResourceSpec` в `RESOURCES`, прописать пару
  `<source>` → `<dest>` в `[tool.hatch.build.targets.wheel.force-include]` в `pyproject.toml`.

### `prompts.py`

- `PROMPTS` — список `PromptSpec(name, title, description, arguments, builder)`.
- `builder(args)` — pure-функция, которая валидирует аргументы и возвращает текст шаблона.
- При ошибке валидации поднимает `ValidationError` (обрабатывается в `server.py`).
- Шаблоны указывают агенту **что вызвать**, **в каком порядке**, **на что обратить внимание**
  и **как структурировать финальный ответ**.

### `server.py`

- Тонкий — только `app`, `_get_client()`, регистрация декораторов и `run()`.
- `run()` гарантирует `await client.aclose()` через `try/finally`.

### Именование инструментов

Паттерн: `get_<resource>` для получения данных, `search` для поиска.

| Инструмент | Метод API |
|---|---|
| `resolve` | `/search`, либо `/company`/`/entrepreneur`/`/person`/`/bank` при вводе цифр |
| `profile` | `/company`, `/entrepreneur`, `/person` или `/bank` — по числу цифр |
| `due_diligence_report` | каскад: карточка + `/finances` + `/legal-cases` + `/enforcements` + `/fedresurs` + `/bankruptcy-messages` |
| `bankruptcy_risk` | каскад: карточка + `/bankruptcy-messages` + `/fedresurs` + `/enforcements` + `/finances` |
| `get_finances` | `/finances` |
| `get_legal_cases` | `/legal-cases` |
| `get_contracts` | `/contracts` |
| `get_inspections` | `/inspections` |
| `get_enforcements` | `/enforcements` |
| `get_bank` | `/bank` |
| `get_timeline` | `/timeline` |
| `get_fedresurs` | `/fedresurs` |
| `get_bankruptcy_messages` | `/bankruptcy-messages` |

Каскадные инструменты (`resolve`, `profile`, оба отчёта) задаются полем `handler`, обёртки —
полем `endpoint`; `ToolSpec.__post_init__` требует ровно одно из двух. Эндпоинты, которые
задействуют каскады, перечислены в `HANDLER_ENDPOINTS` — без этого тест покрытия методов API
решит, что метод остался без инструмента.

---

## Как добавить новый инструмент

При появлении нового эндпоинта в Checko API:

1. **Документация эндпоинта** — добавить `docs/api/<endpoint>.md` с параметрами и форматом ответа.
2. **Pre-валидатор** — добавить `_xxx_pre(args)` в `tools.py` (или переиспользовать `_id_required_pre`).
3. **Реестр** — добавить `ToolSpec(...)` в список `TOOLS` в `tools.py`.
4. **Тесты** — обязательны три места:
   - имя в `EXPECTED_TOOLS` в `tests/test_tools.py` и проверка pre-валидатора;
   - параметры метода в `API_PARAMS` в `tests/test_api_contract.py` — это источник истины,
     схема не должна объявлять ничего сверх него;
   - wire-кейс в `WIRE_CASES` — какой именно путь и query-параметры уходят в API. Без него
     ошибка в имени параметра не ловится ничем (так `/entrepreneur` получал `ogrnip`).
   - счётчик `EXPECTED_TOOLS` в `scripts/smoke.py`.
5. **Документация для агента** — обновить `docs/instructions/agent-guide.md` (поля, риски, анти-паттерны для нового инструмента).
6. **Индексы** — обновить `docs/api/README.md`, `README.md`, `AGENTS.md` (этот файл, таблица выше).
7. **Changelog** — добавить запись в `## [Unreleased]` секцию `CHANGELOG.md`.

## Как добавить новый prompt

1. Добавить builder-функцию `_xxx(args)` в `prompts.py`.
2. Добавить `PromptSpec(...)` в `PROMPTS`.
3. Добавить тесты в `tests/test_prompts.py`:
   - имя в `EXPECTED_PROMPTS`;
   - проверки builder'а (минимальный набор args, опциональные args, ошибки валидации).
4. Упомянуть prompt в `docs/instructions/agent-guide.md` в секции «Готовые сценарии».
5. Упомянуть в `README.md` в таблице prompts.

## Как добавить новый resource

1. Создать markdown-файл в `docs/`, `playbooks/` или корне репозитория (canonical location).
2. Добавить `ResourceSpec(...)` в `RESOURCES` в `resources.py` (указать `file_name` и `repo_path`).
3. Добавить пару `<repo path>` → `checko_mcp/_resources/<file_name>` в `[tool.hatch.build.targets.wheel.force-include]` в `pyproject.toml`.
4. Если ресурс не в `docs/`, `playbooks/` или корне — обновить `Dockerfile` (`COPY ...`).
5. Добавить URI в `EXPECTED_URIS` в `tests/test_resources.py` и smoke-проверку контента.
6. Упомянуть URI в таблице ресурсов в `agent-guide.md` и `README.md`.

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|:---:|---|
| `CHECKO_API_KEY` | да | API-ключ Checko.ru ([получить](https://checko.ru/user/account/api)) |
| `CHECKO_BASE_URL` | нет | Базовый URL (по умолчанию `https://api.checko.ru/v2`) |
| `CHECKO_TIMEOUT` | нет | Таймаут запроса в секундах (по умолчанию `30`) |
| `CHECKO_RETRIES` | нет | Повторы при HTTP 429 и 5xx (по умолчанию `3`) |
| `CHECKO_CACHE_TTL` | нет | Время жизни кэша ответов, сек. (по умолчанию `900`, `0` отключает) |

---

## Запуск и разработка

```bash
git clone https://github.com/Nymaxxx/checko-mcp.git
cd checko-mcp

python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

pip install -e ".[dev]"

cp .env.example .env
# редактируем .env: CHECKO_API_KEY=...

ruff check src/ tests/
pytest -q

python -m checko_mcp              # запуск сервера (ожидает stdio)
```

### Docker

```bash
docker compose build
docker compose run --rm -i checko-mcp     # ручной тест stdio
```

### Smoke-тест перед релизом

Скрипт `scripts/smoke.py` запускает реального MCP-клиента, проходит по всем слоям (tools / resources / prompts) и опционально делает реальный вызов API:

```bash
python scripts/smoke.py                # против локального python -m checko_mcp
python scripts/smoke.py --docker       # против собранного docker compose
python scripts/smoke.py --no-api       # только структурные проверки, без обращения к Checko
```

Смок-тест должен показать `16/16 checks passed` без реального вызова API (`17/17` с ним).
Запускать перед каждой публикацией версии. Шаг `--no-api` включён в CI: без него мажорный
апгрейд MCP SDK проходит проверки незамеченным, потому что unit-тесты реестров не поднимают
сервер.

---

## Известные особенности API

- **Данные арбитражных дел** обновляются с задержкой ~1–2 недели.
- **ИНН юрлица** не уникален при наличии филиалов — API возвращает головную организацию.
- **Физлицо** идентифицируется только по ИНН (12 цифр). Организации человека ищутся через
  `/search` с `by=founder-name` или `by=leader-name`.
- **У `/entrepreneur` параметр называется `ogrn`, а не `ogrnip`**, хотя несёт ОГРНИП.
  На `ogrnip` метод отвечает `HTTP 400`.
- **Булевы параметры** должны передаваться в API как строка `"true"` — этим занимается
  `coerce_bool`. Значение `false` нужно убирать из запроса целиком: строку `"false"`
  API трактует как включённый флаг.
- **`/search` не имеет `date_from`/`date_to`.** Неизвестные параметры молча игнорируются,
  поэтому объявлять в схеме то, чего у метода нет, опаснее, чем не объявлять ничего.
- **Ответы очень объёмные:** расширенная отчётность до 152 тыс. символов, карточка крупной
  организации до 113 тыс. MCP-клиенты обрезают вывод молча, отсюда `detail=compact`
  по умолчанию.
- **Тарифы:** 100 запросов в сутки бесплатно, далее 0,10–0,15 руб. за запрос. На бесплатном
  тарифе `meta.balance` равен 0 постоянно — признак исчерпания это `meta.today_request_count`,
  а не нулевой баланс.
- **Белорусских данных в API нет.** На УНП приходит `200` с пустым `data`, а не ошибка.
- Версия API **2.4** (02.2026) добавила `/timeline`, `/fedresurs`, `/bankruptcy-messages`,
  `СвязУчред` в `/company` и `codes=all` в `/search`. Метод `/enforcements` есть с версии 2.0.

---

## Changelog проекта

См. [`CHANGELOG.md`](CHANGELOG.md). Любое изменение добавляется в секцию `## [Unreleased]` с разбивкой по типу (Added / Changed / Fixed / Removed).
