# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-05

Первый публичный релиз.

### Added

#### MCP-инструменты (12)

- `search` — поиск по ЕГРЮЛ/ЕГРИП по названию или ОКВЭД (обязательные `by`/`obj`/`query`).
- `get_company` — данные ЕГРЮЛ.
- `get_entrepreneur` — данные ЕГРИП.
- `get_person` — профиль физлица по ИНН (12 цифр).
- `get_finances` — финансовая отчётность.
- `get_legal_cases` — арбитражные дела.
- `get_contracts` — госконтракты (обязательный `law`: `44` или `223`, опциональный `role`).
- `get_inspections` — проверки.
- `get_bank` — справочник банков по БИК.
- `get_timeline` — хронология изменений (API v2.4).
- `get_fedresurs` — сообщения Федресурса (API v2.4).
- `get_bankruptcy_messages` — записи ЕФРСБ (API v2.4).

#### MCP-сценарии (6 prompts)

- `check_counterparty(query, purpose?)` — комплексная проверка контрагента.
- `verify_bank_details(inn, bic)` — проверка платёжных реквизитов.
- `assess_bankruptcy_risk(inn, context?)` — оценка риска банкротства.
- `audit_person(inn, purpose?)` — аудит физлица по методологии.
- `evaluate_tender_participant(query, purpose?)` — оценка участника тендера (44-ФЗ + 223-ФЗ).
- `analyze_finances(ogrn_or_inn, years?)` — динамика финансовых показателей.

#### MCP-ресурсы (5 справочных markdown)

- `checko://docs/agent-guide` — гайд для AI-агентов с приоритизированными факторами риска и анти-паттернами.
- `checko://docs/legal` — правовая справка (152-ФЗ, 149-ФЗ).
- `checko://playbooks/audit/methodology` — методология аудита.
- `checko://playbooks/audit/anomaly-checklist` — чек-лист аномалий.
- `checko://playbooks/audit/template` — шаблон отчёта.

#### Архитектура и качество

- Модульная структура `src/checko_mcp/`: `server.py`, `tools.py`, `prompts.py`, `resources.py`, `client.py`, `_validation.py`.
- `CheckoClient` использует один `httpx.AsyncClient` на весь lifespan сервера; корректное `aclose()` через `try/finally`.
- Серверная валидация форматов ИНН, ОГРН, ОГРНИП, БИК.
- 83 unit-теста (`pytest` + `pytest-asyncio` + `httpx.MockTransport`).
- End-to-end smoke-тест через настоящий MCP-клиент по stdio (`scripts/smoke.py`, поддерживает `--docker` и `--no-api`; реальный API-вызов опционален через `SMOKE_TEST_BIC`).
- GitHub Actions CI: lint (`ruff`) + тесты на Python 3.10–3.13 + сборка Docker-образа (`.github/workflows/ci.yml`).
- Поддержка переменных окружения `CHECKO_BASE_URL` и `CHECKO_TIMEOUT`.

#### Документация

- README с быстрым стартом через `docker compose`, обзором tools/prompts/resources, бэйджами и дисклеймером «не аффилирован с Checko.ru».
- Справочник по эндпоинтам API в `docs/api/`.
- Гайд для AI-агентов в `docs/instructions/agent-guide.md` (приоритизированные факторы риска, анти-паттерны).
- Методология и шаблоны due-diligence в `playbooks/audit/`.
- `AGENTS.md` — инструкция для разработчиков (как добавить tool/prompt/resource).
- `CONTRIBUTING.md`, `SECURITY.md`, `LEGAL.md`, `.github/PULL_REQUEST_TEMPLATE.md`.

#### Сборка и упаковка

- `[tool.hatch.build.targets.wheel.force-include]` упаковывает канонические markdown в `checko_mcp/_resources/` (для `importlib.resources`).
- `[project.optional-dependencies] dev`: `pytest`, `pytest-asyncio`, `ruff`.
- Билингвальное описание пакета (RU + EN) и расширенные классификаторы PyPI.
- Multi-stage Dockerfile.

### Security / Privacy

- В репозитории нет ни одного настоящего ИНН/ОГРН/КПП/ОКПО/ФИО/адреса — только синтетические placeholder'ы (`1234567890`, `1234567890123`, `Иванов Иван Иванович`, `ООО «Тестовая Компания»` и т.п.).
- `scripts/smoke.py` делает реальный API-вызов только если в окружении задан `SMOKE_TEST_BIC` (по умолчанию пропускается); в коде нет жёстко зашитых идентификаторов.
- В `AGENTS.md` зафиксировано правило использовать только синтетические идентификаторы; в `.env.example` — пояснение по `SMOKE_TEST_BIC`.
- `LEGAL.md` описывает ограничения 152-ФЗ и условий Checko.ru API.
