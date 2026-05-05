# AGENTS.md — Руководство для AI-агентов и разработчиков

Этот файл описывает структуру проекта, соглашения по коду и инструкции для AI-агентов, работающих над этим репозиторием.

---

## Обзор проекта

**checko-mcp** — Python MCP-сервер для [Checko.ru API v2](https://checko.ru/integration/api).
Предоставляет AI-ассистентам и MCP-клиентам:

- **12 инструментов** (tools) — вызовы эндпоинтов API.
- **6 готовых сценариев** (prompts) — типовые workflow с зашитой последовательностью вызовов.
- **5 справочных ресурсов** (resources) — agent guide, правовая справка, методология аудита.

**Стек:**
- Python 3.10+ (CI: 3.10/3.11/3.12/3.13)
- `mcp[cli]` — Python MCP SDK (stdio-транспорт)
- `httpx` — async HTTP-клиент (один экземпляр на жизнь сервера)
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
│       ├── client.py          — CheckoClient (httpx.AsyncClient + CheckoAPIError)
│       ├── tools.py           — реестр TOOLS: список ToolSpec(name, endpoint, schema, pre)
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

| Инструмент | Эндпоинт |
|---|---|
| `search` | `/search` |
| `get_company` | `/company` |
| `get_entrepreneur` | `/entrepreneur` |
| `get_person` | `/person` |
| `get_finances` | `/finances` |
| `get_legal_cases` | `/legal-cases` |
| `get_contracts` | `/contracts` |
| `get_inspections` | `/inspections` |
| `get_bank` | `/bank` |
| `get_timeline` | `/timeline` |
| `get_fedresurs` | `/fedresurs` |
| `get_bankruptcy_messages` | `/bankruptcy-messages` |

---

## Как добавить новый инструмент

При появлении нового эндпоинта в Checko API:

1. **Документация эндпоинта** — добавить `docs/api/<endpoint>.md` с параметрами и форматом ответа.
2. **Pre-валидатор** — добавить `_xxx_pre(args)` в `tools.py` (или переиспользовать `_id_required_pre`).
3. **Реестр** — добавить `ToolSpec(...)` в список `TOOLS` в `tools.py`.
4. **Тесты** — добавить case в `tests/test_tools.py`:
   - имя в `EXPECTED_TOOLS`;
   - проверка pre-валидатора (отсутствие обязательных, неверный формат, конвертация bool).
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

Смок-тест должен показать `17/17 checks passed` (или `16/16` без API). Запускать перед каждой публикацией версии.

---

## Известные особенности API

- **Данные арбитражных дел** обновляются с задержкой ~1–2 недели.
- **ИНН юрлица** не уникален при наличии филиалов — API возвращает головную организацию.
- **Физлицо** идентифицируется только по ИНН (12 цифр), поиск по ФИО недоступен.
- **Булевы параметры** должны передаваться в API как строка `"true"` — этим занимается `coerce_bool`.
- Версия API **2.4** (02.2026) добавила `/timeline`, `/fedresurs`, `/bankruptcy-messages`.

---

## Changelog проекта

См. [`CHANGELOG.md`](CHANGELOG.md). Любое изменение добавляется в секцию `## [Unreleased]` с разбивкой по типу (Added / Changed / Fixed / Removed).
