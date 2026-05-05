# Checko MCP Server

[![CI](https://github.com/Nymaxxx/checko-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Nymaxxx/checko-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-stdio-purple)](https://modelcontextprotocol.io/)

MCP-сервер для [Checko.ru API v2](https://checko.ru/integration/api) — проверка российских компаний, ИП, физлиц и юридических данных прямо из любого AI-ассистента, поддерживающего [Model Context Protocol](https://modelcontextprotocol.io/).

> **Неофициальный community-проект.** Не аффилирован с ООО «Чекко». Использует публичный API Checko.ru — нужен собственный API-ключ.

---

## Что внутри

Сервер выставляет три типа возможностей MCP:

- **12 инструментов** (tools) — прямой доступ к эндпоинтам Checko API.
- **6 готовых сценариев** (prompts) — типовые workflow с уже зашитой последовательностью вызовов: `check_counterparty`, `verify_bank_details`, `assess_bankruptcy_risk`, `audit_person`, `evaluate_tender_participant`, `analyze_finances`.
- **5 справочных ресурсов** (resources) — agent guide, правовая справка (152-ФЗ), методология аудита физлица.

### Инструменты

| Инструмент | Описание |
|---|---|
| `search` | Поиск компаний и ИП по названию, ИНН, ОГРН, ОКВЭД и другим критериям |
| `get_company` | Данные ЕГРЮЛ по организации (ОГРН или ИНН) |
| `get_entrepreneur` | Данные ЕГРИП по индивидуальному предпринимателю |
| `get_person` | Информация о физическом лице по ИНН |
| `get_finances` | Финансовая отчётность организации (Росстат, ГИР БО ФНС) |
| `get_legal_cases` | Арбитражные дела с фильтрацией по роли, датам и сумме иска |
| `get_contracts` | Государственные контракты по 44-ФЗ и 223-ФЗ |
| `get_inspections` | Проверки организации или ИП |
| `get_bank` | Информация о банке по БИК |
| `get_timeline` | История изменений организации, ИП или физлица |
| `get_fedresurs` | Сообщения Федресурса (ЕФРСФДЮЛ) |
| `get_bankruptcy_messages` | Записи ЕФРСБ (реестр банкротств) |

---

## Быстрый старт (Docker Compose)

Самый простой путь — собрать образ один раз и подключить как stdio-сервер.

### 1. Получите API-ключ Checko

[checko.ru/user/account/api](https://checko.ru/user/account/api) — потребуется регистрация.

### 2. Соберите образ

```bash
git clone https://github.com/Nymaxxx/checko-mcp.git
cd checko-mcp

cp .env.example .env
# отредактируйте .env: CHECKO_API_KEY=ваш_ключ

docker compose build
```

### 3. Подключите к MCP-клиенту

Откройте файл конфигурации MCP вашего AI-клиента (любого, поддерживающего stdio-серверы) и добавьте запись. Замените `/абсолютный/путь/checko-mcp` на путь к клонированному репозиторию:

```json
{
  "mcpServers": {
    "checko": {
      "command": "docker",
      "args": [
        "compose",
        "-f", "/абсолютный/путь/checko-mcp/docker-compose.yml",
        "run", "--rm", "-i", "checko-mcp"
      ]
    }
  }
}
```

`CHECKO_API_KEY` подхватится из `.env` автоматически (через `env_file` в `docker-compose.yml`).

Проверьте — перезапустите MCP-клиент. Сервер должен появиться в списке доступных инструментов.

---

## Альтернативные способы запуска

<details>
<summary><b>Через <code>docker run</code> (без compose)</b></summary>

```bash
docker build -t checko-mcp:latest .
```

```json
{
  "mcpServers": {
    "checko": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "CHECKO_API_KEY=ваш_ключ",
        "checko-mcp:latest"
      ]
    }
  }
}
```

</details>

<details>
<summary><b>Через локальный Python (pip)</b></summary>

```bash
git clone https://github.com/Nymaxxx/checko-mcp.git
cd checko-mcp

python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

pip install -e .
```

```json
{
  "mcpServers": {
    "checko": {
      "command": "/абсолютный/путь/checko-mcp/.venv/bin/python",
      "args": ["-m", "checko_mcp"],
      "env": {
        "CHECKO_API_KEY": "ваш_ключ"
      }
    }
  }
}
```

> На Windows путь до интерпретатора выглядит так: `C:\\путь\\checko-mcp\\.venv\\Scripts\\python.exe`.

</details>

<details>
<summary><b>Через <code>uvx</code> (после публикации на PyPI)</b></summary>

```json
{
  "mcpServers": {
    "checko": {
      "command": "uvx",
      "args": ["checko-mcp"],
      "env": { "CHECKO_API_KEY": "ваш_ключ" }
    }
  }
}
```

> Доступно после публикации пакета на PyPI.

</details>

---

## Готовые сценарии (prompts)

В большинстве случаев ручной pipeline не нужен — вызовите подходящий prompt, в котором уже зашита правильная последовательность инструментов и шаблон финального ответа.

| Prompt | Аргументы | Назначение |
|---|---|---|
| `check_counterparty` | `query`, `purpose?` | Комплексная проверка контрагента: search → company → finances → legal_cases → fedresurs → bankruptcy |
| `verify_bank_details` | `inn`, `bic` | Проверка платёжных реквизитов: get_company/get_entrepreneur + get_bank |
| `assess_bankruptcy_risk` | `inn`, `context?` | Оценка риска банкротства по 4 источникам сигналов |
| `audit_person` | `inn`, `purpose?` | Полный аудит физлица по методологии (требует законного основания) |
| `evaluate_tender_participant` | `query`, `purpose?` | Оценка участника тендера: контракты, проверки, иски, финансы |
| `analyze_finances` | `ogrn_or_inn`, `years?` | Динамика выручки, прибыли, капитала за N лет |

В большинстве MCP-клиентов prompts видны как явные команды (slash-меню) и появляются в списке после подключения сервера.

## Справочные ресурсы

Сервер также экспонирует markdown-справочники, которые AI-клиент может подгрузить в контекст:

| URI | Содержание |
|-----|-----------|
| `checko://docs/agent-guide` | Agent guide: правила, поля ответов, факторы риска, анти-паттерны |
| `checko://docs/legal` | Правовые ограничения (152-ФЗ, 149-ФЗ) |
| `checko://playbooks/audit/methodology` | Полная методология аудита физлица |
| `checko://playbooks/audit/anomaly-checklist` | Чеклист аномалий с приоритизацией |
| `checko://playbooks/audit/template` | Шаблон отчёта аудита |

---

## Конфигурация

| Переменная | Обязательная | Описание |
|---|:---:|---|
| `CHECKO_API_KEY` | да | API-ключ Checko.ru |
| `CHECKO_BASE_URL` | нет | Базовый URL (по умолчанию `https://api.checko.ru/v2`, полезно для тестов) |
| `CHECKO_TIMEOUT` | нет | Таймаут запроса в секундах (по умолчанию `30`) |

---

## Документация

- [`docs/api/`](docs/api/) — справочник по эндпоинтам Checko API
- [`docs/instructions/agent-guide.md`](docs/instructions/agent-guide.md) — agent guide (он же экспонируется как ресурс `checko://docs/agent-guide`)
- [`playbooks/audit/`](playbooks/audit/) — методология и шаблоны аудита физлица (экспонируется как ресурсы `checko://playbooks/audit/*`)
- [`AGENTS.md`](AGENTS.md) — соглашения по коду и инструкции для разработчика
- [`CHANGELOG.md`](CHANGELOG.md) — история версий
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — как внести вклад
- [`SECURITY.md`](SECURITY.md) — как сообщить об уязвимости
- [`LEGAL.md`](LEGAL.md) — правовые основания (152-ФЗ, 149-ФЗ)

---

## Разработка

```bash
git clone https://github.com/Nymaxxx/checko-mcp.git
cd checko-mcp

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check src/ tests/
pytest -q
```

CI прогоняет lint + тесты на Python 3.10–3.13 для каждого PR.

---

## Правовые ограничения

Сервер предоставляет доступ к публично раскрытым сведениям государственных реестров (ЕГРЮЛ, ЕГРИП, ГИР БО ФНС, Росстат, КАД, ЕФРСФДЮЛ, ЕФРСБ).

- Использование данных о физических лицах регулируется **Федеральным законом от 27.07.2006 № 152-ФЗ** «О персональных данных». Пользователь самостоятельно обеспечивает соответствие своей деятельности требованиям законодательства.
- Сервер является программной обёрткой над API Checko.ru. Пользователь обязан ознакомиться с [условиями использования Checko.ru](https://checko.ru/integration/api) и соблюдать их.
- Массовый автоматизированный сбор персональных данных физических лиц без законного основания недопустим.

Подробнее — [`LEGAL.md`](LEGAL.md).

---

## Лицензия

[MIT](LICENSE).
