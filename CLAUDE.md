# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

MCP-сервер (stdio) поверх Checko.ru API v2: 12 инструментов, 6 prompts, 5 markdown-ресурсов.
Python 3.10+, `mcp[cli]` + `httpx`, сборка через hatchling, линт `ruff`, тесты `pytest`.

Подробные соглашения по коду, чеклисты добавления инструментов/prompts/ресурсов и особенности
Checko API - в [`AGENTS.md`](AGENTS.md). Этот файл не дублирует его, а дает быстрый вход.

## Команды

```bash
pip install -e ".[dev]"        # окружение разработки

ruff check src/ tests/         # линт (то же, что в CI)
ruff check --fix src/ tests/
pytest -q                      # все тесты

pytest tests/test_tools.py -q                                  # один файл
pytest tests/test_tools.py::TestPreValidators -q                # один класс
pytest tests/test_tools.py::TestPreValidators::test_company_requires_id -q
pytest -k coerce -q                                             # по подстроке

python -m checko_mcp           # запуск сервера (ждет MCP-клиента на stdin/stdout)
```

End-to-end smoke-тест (запускает реального MCP-клиента через stdio и проходит все три слоя):

```bash
python scripts/smoke.py            # против python -m checko_mcp
python scripts/smoke.py --docker   # против docker compose (нужен docker compose build)
python scripts/smoke.py --no-api   # только структурные проверки
```

Ожидаемый результат - `17/17 checks passed` (`16/16` без реального вызова API). Реальный вызов
происходит только при заданном `SMOKE_TEST_BIC` в `.env`; настоящих идентификаторов в коде нет.

Docker: `docker compose build`, затем `docker compose run --rm -i checko-mcp`.

CI (`.github/workflows/ci.yml`): `ruff check src/ tests/` + `pytest -q` на Python 3.10-3.13,
плюс отдельная сборка Docker-образа.

## Архитектура

Три параллельных реестра, `server.py` - тонкий диспетчер без бизнес-логики:

```
MCP-клиент ──stdio──▶ server.py ──▶ tools.py     (TOOLS / TOOLS_BY_NAME)   ──▶ client.py ──▶ api.checko.ru/v2
                              ├──▶ resources.py (RESOURCES / RESOURCES_BY_URI)
                              └──▶ prompts.py   (PROMPTS / PROMPTS_BY_NAME)
```

Все три модуля устроены одинаково: frozen dataclass-спецификация (`ToolSpec`, `ResourceSpec`,
`PromptSpec`) + список + индекс по ключу. Добавление возможности = добавление записи в список,
а не правка `server.py`.

**Путь tool-вызова:** `call_tool` находит `ToolSpec` → `spec.pre(arguments)` валидирует и **мутирует
аргументы на месте** → `CheckoClient.get(spec.endpoint, **arguments)` → ответ отдается
pretty-printed JSON. `ValidationError` и `CheckoAPIError` не пробрасываются наружу, а
превращаются в текст `Ошибка: ...` (`_error()` в `server.py`), поэтому у неуспешного вызова
инструмента нормальный `TextContent`, а не MCP-ошибка.

**Клиент:** один `httpx.AsyncClient` на весь срок жизни процесса, ленивая инициализация через
`_get_client()`, закрытие в `finally` внутри `run()`. `key` добавляется автоматически,
`None`-параметры отфильтровываются. Ошибкой считается не только HTTP-статус, но и
`meta.status == "error"` в теле 200-ответа. Для тестов в конструктор передается
`transport=httpx.MockTransport(...)` - сеть в тестах не используется.

**Ресурсы читаются из двух мест.** Канонические markdown-файлы живут в `docs/instructions/`,
`playbooks/audit/` и `LEGAL.md`; при сборке wheel hatchling копирует их в
`checko_mcp/_resources/` через `[tool.hatch.build.targets.wheel.force-include]`.
`_load_text()` сначала пробует package data (`importlib.resources`), при отсутствии падает в
fallback по `Path(__file__).parents[2] / spec.repo_path`. Отсюда связка: новый ресурс требует
записи и в `RESOURCES`, и в `force-include` в `pyproject.toml`, иначе он работает в dev и ломается
в wheel/Docker.

## Что легко сломать

- **Счетчики продублированы.** `scripts/smoke.py` хардкодит `EXPECTED_TOOLS = 12`,
  `EXPECTED_RESOURCES = 5`, `EXPECTED_PROMPTS = 6`; тесты - множества `EXPECTED_TOOLS`,
  `EXPECTED_URIS`, `EXPECTED_PROMPTS`. Любая новая возможность = правка обоих мест
  (полный чеклист - в `AGENTS.md`).
- **Булевы параметры Checko API принимает только строкой `"true"`.** Этим занимается
  `coerce_bool(args, ...)`: `True → "true"`, `False → None` (параметр исчезает). Новый
  boolean-флаг без вызова `coerce_bool` в pre-валидаторе уйдет в API как `True` и не сработает.
- **`filterwarnings = ["error"]`** в pytest-конфиге: любой warning валит тест.
  `asyncio_mode = "auto"` - `@pytest.mark.asyncio` не нужен.
- **`ruff` line-length 100**, но `tools.py`, `prompts.py` и `tests/*` исключены из E501
  (длинные русские описания); `playbooks/` и `docs/` из линта исключены целиком.
- **Только синтетические идентификаторы** в коде, тестах и docs: ИНН-10 `1234567890`,
  ИНН-12 `123456789012`, ОГРН `1234567890123`, ОГРНИП `123456789012345`, БИК `123456789`.
  Настоящие ИНН/ОГРН/БИК/ФИО в репозиторий не попадают - реальный БИК только через
  `SMOKE_TEST_BIC` в локальном `.env`.
- Сообщения об ошибках, описания инструментов и docstrings - на русском, это осознанно
  (локализованный инструмент). Типизация обязательна.

## Формат prompts

`builder(args)` - чистая функция: валидирует аргументы (`_required` / `check_format`) и
возвращает готовый текст. Текст адресован AI-агенту и задает конкретную последовательность
вызовов инструментов, поля ответа, на которые смотреть, и структуру финального отчета -
менять его стоит вместе с `docs/instructions/agent-guide.md`, чтобы формулировки не расходились.

## Правовой контекст

Инструмент работает с данными о физлицах (`get_person`, prompt `audit_person`). Ограничения
152-ФЗ/149-ФЗ описаны в `LEGAL.md` (он же ресурс `checko://docs/legal`) и учтены в текстах
prompts - при правках не убирайте требование законного основания.
