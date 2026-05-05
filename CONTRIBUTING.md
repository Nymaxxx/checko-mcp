# Участие в разработке

## Как сообщить об ошибке

Используйте [GitHub Issues](https://github.com/Nymaxxx/checko-mcp/issues/new?template=bug_report.md). Укажите:

- версию Python и ОС
- команду или инструмент MCP, который вызвал ошибку
- полный текст ошибки (без API-ключей)

## Как предложить улучшение

Создайте [Issue](https://github.com/Nymaxxx/checko-mcp/issues/new?template=feature_request.md) с описанием задачи и желаемого поведения.

## Как внести изменения в код

1. Форкните репозиторий и создайте ветку от `main`:
   ```bash
   git checkout -b feat/название-фичи
   ```

2. Установите зависимости для разработки (вместе с dev-extras):
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   # .venv\Scripts\activate    # Windows
   pip install -e ".[dev]"
   ```

3. Внесите изменения, соблюдая соглашения кодовой базы:
   - типизация обязательна (`from typing import Any`)
   - строки до 100 символов (PEP 8)
   - комментарии только там, где код сам по себе неочевиден
   - русскоязычные сообщения об ошибках (это локализованный инструмент)

4. Прогоните lint и тесты локально:
   ```bash
   ruff check src/ tests/
   pytest -q
   ```

5. (опционально) Прогоните end-to-end smoke-тест:
   ```bash
   python scripts/smoke.py            # требует CHECKO_API_KEY в .env (или --no-api)
   python scripts/smoke.py --docker   # после docker compose build
   ```

6. Добавьте/обновите тесты для своих изменений в `tests/`.

7. Обновите `CHANGELOG.md` (секция `## [Unreleased]`).

8. Создайте Pull Request — шаблон с чеклистом подгрузится автоматически.

## Как добавить новый эндпоинт Checko API

Следуйте инструкции в [`AGENTS.md`](AGENTS.md#как-добавить-новый-инструмент) — там описан полный чеклист.

## Стиль кода

Проект использует `ruff` для линтинга и форматирования. Конфигурация — в `pyproject.toml` (секция `[tool.ruff]`).

```bash
ruff check src/ tests/        # проверка
ruff check --fix src/ tests/  # автоисправление
```

## Вопросы

Открывайте [Discussion](https://github.com/Nymaxxx/checko-mcp/discussions) или Issue с меткой `question`.
