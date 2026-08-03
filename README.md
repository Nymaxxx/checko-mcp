# Checko MCP Server

[![CI](https://github.com/mazixs/checko-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/mazixs/checko-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-stdio-purple)](https://modelcontextprotocol.io/)

MCP-сервер для [Checko.ru API v2](https://checko.ru/integration/api) — проверка российских компаний, ИП, физлиц и юридических данных прямо из любого AI-ассистента, поддерживающего [Model Context Protocol](https://modelcontextprotocol.io/).

> **Неофициальный community-проект.** Не аффилирован с ООО «Чекко». Использует публичный API Checko.ru — нужен собственный API-ключ.

> [!WARNING]
> **Этот сервер — MCP-инструмент, а не самостоятельный агент.** Данные берутся из API Checko.ru, но интерпретирует и излагает их AI-ассистент, к которому вы подключили сервер. AI-модели могут ошибаться: путать поля ответа, делать неверные выводы, галлюцинировать факты или пропускать важные детали. **Перед принятием любых деловых, юридических или финансовых решений самостоятельно проверяйте ключевые сведения в первоисточниках** (ЕГРЮЛ/ЕГРИП на сайте ФНС, КАД.Арбитр, ЕФРСБ и т. д.).

---

## Что внутри

Сервер выставляет три типа возможностей MCP:

- **13 инструментов** (tools) — по одному на каждый метод Checko API.
- **6 готовых сценариев** (prompts) — типовые workflow с уже зашитой последовательностью вызовов: `check_counterparty`, `verify_bank_details`, `assess_bankruptcy_risk`, `audit_person`, `evaluate_tender_participant`, `analyze_finances`.
- **5 справочных ресурсов** (resources) — agent guide, правовая справка (152-ФЗ), методология аудита физлица.

### Инструменты

| Инструмент | Описание |
|---|---|
| `search` | Поиск по наименованию, ФИО **учредителя** или **руководителя**, коду ОКВЭД-2, дате регистрации или обновления |
| `get_company` | Данные ЕГРЮЛ по организации (ОГРН, ИНН или ОКПО) |
| `get_entrepreneur` | Данные ЕГРИП по ИП (ОГРНИП, ИНН или ОКПО) |
| `get_person` | Связи и факторы риска физического лица по ИНН |
| `get_finances` | Финансовая отчётность организации (Росстат, ГИР БО ФНС, с 2011 года) |
| `get_legal_cases` | Арбитражные дела с фильтрами по роли, датам и сумме иска |
| `get_contracts` | Госзакупки по 44-ФЗ, 94-ФЗ и 223-ФЗ, сортировка по сумме |
| `get_inspections` | Проверки организации или ИП |
| `get_enforcements` | **Исполнительные производства ФССП** — открытые взыскания долгов |
| `get_bank` | Информация о банке по БИК |
| `get_timeline` | История изменений организации, ИП или физлица |
| `get_fedresurs` | Сообщения Федресурса (ЕФРСФДЮЛ) |
| `get_bankruptcy_messages` | Записи ЕФРСБ (реестр банкротств) |

> [!IMPORTANT]
> **Только российские реестры.** У портала Checko есть данные по организациям Беларуси (ЕГР Минюста РБ, идентификатор УНП), но в API 2.4 нет ни одного метода для них — все методы работают по ОГРН, ИНН, ОКПО и БИК. Проверить белорусскую компанию через этот сервер нельзя.

---

## Установка

### Шаг 1. Получите API-ключ

[checko.ru/user/account/api](https://checko.ru/user/account/api) — нужна регистрация. Бесплатный тариф: 100 запросов в сутки.

### Шаг 2. Установите `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # Linux / macOS
```

`uv` приносит с собой `uvx`, который скачает и запустит сервер сам — ни `git clone`, ни venv, ни Docker не нужны.

### Шаг 3. Подключите к своему клиенту

Подставьте свой ключ вместо `ВАШ_КЛЮЧ` и выполните **одну** строку.

**Claude Code**

```bash
# глобально — во всех проектах
claude mcp add --env CHECKO_API_KEY=ВАШ_КЛЮЧ --scope user checko -- uvx --from git+https://github.com/mazixs/checko-mcp checko-mcp

# только в текущем проекте (запишется в .mcp.json и поедет с репозиторием)
claude mcp add --env CHECKO_API_KEY=ВАШ_КЛЮЧ --scope project checko -- uvx --from git+https://github.com/mazixs/checko-mcp checko-mcp
```

**Codex CLI**

```bash
# глобально — пишет в ~/.codex/config.toml
codex mcp add checko --env CHECKO_API_KEY=ВАШ_КЛЮЧ -- uvx --from git+https://github.com/mazixs/checko-mcp checko-mcp
```

Для одного проекта создайте `.codex/config.toml` в его корне:

```toml
[mcp_servers.checko]
command = "uvx"
args = ["--from", "git+https://github.com/mazixs/checko-mcp", "checko-mcp"]

[mcp_servers.checko.env]
CHECKO_API_KEY = "ВАШ_КЛЮЧ"
```

**Antigravity**

CLI-команды нет — добавьте запись в файл. Глобально: `~/.gemini/config/mcp_config.json`. Для одного проекта: `.agents/mcp_config.json` в его корне.

```json
{
  "mcpServers": {
    "checko": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mazixs/checko-mcp", "checko-mcp"],
      "env": { "CHECKO_API_KEY": "ВАШ_КЛЮЧ" }
    }
  }
}
```

### Шаг 4. Проверьте

Перезапустите клиент и спросите его: «проверь контрагента по ИНН 7707049388». В Claude Code список серверов и их состояние показывает `claude mcp list`.

> [!NOTE]
> Пакет `checko-mcp` на PyPI — это исходный проект `Nymaxxx/checko-mcp`, а не этот форк. Команды выше ставят форк из git, поэтому `uvx checko-mcp` без `--from` использовать не нужно.

---

## Альтернативные способы запуска

<details>
<summary><b>Через Docker Compose</b></summary>

```bash
git clone https://github.com/mazixs/checko-mcp.git
cd checko-mcp

cp .env.example .env
# отредактируйте .env: CHECKO_API_KEY=ваш_ключ

docker compose build
```

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

`CHECKO_API_KEY` подхватится из `.env` автоматически.

</details>

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
git clone https://github.com/mazixs/checko-mcp.git
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

- [`docs/examples.md`](docs/examples.md) — комплексные примеры использования (распутывание схемы, batch-фильтрация, анализ номинала, реконструкция нарратива)
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
git clone https://github.com/mazixs/checko-mcp.git
cd checko-mcp

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check src/ tests/
pytest -q
pytest -q --cov=checko_mcp --cov-report=term-missing
```

CI на каждый PR: lint и тесты на Python 3.11–3.14, реальный MCP-хендшейк через `scripts/smoke.py --no-api` и сборка Docker-образа.

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
