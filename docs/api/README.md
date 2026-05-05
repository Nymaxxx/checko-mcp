# Checko.ru API v2 — Полная документация

Источник: https://checko.ru/integration/api  
Актуальная версия: **2.4** (4 февраля 2026)

## Общее

- Базовый URL: `https://api.checko.ru/v2`
- Метод запросов: **GET** или **POST**
- Авторизация: параметр `key=API_KEY` в каждом запросе
- Ответ: JSON
- SSL: поддерживается (`https://`), также работает `http://` (порт 80, для совместимости с 1С)

## Структура ответа

Каждый ответ содержит блок `meta`:

```json
{
  "meta": {
    "status": "ok",
    "today_request_count": 42,
    "balance": 1500.00,
    "message": "..."
  }
}
```

| Поле | Описание |
|------|----------|
| `status` | `"ok"` или `"error"` |
| `today_request_count` | Количество запросов за сегодня |
| `balance` | Остаток баланса, руб. |
| `message` | Текст ошибки (только при `status: "error"`) |

## Эндпоинты

| Файл | Эндпоинт | Описание |
|------|----------|----------|
| [search.md](search.md) | `/search` | Поиск компаний и ИП |
| [company.md](company.md) | `/company` | Данные ЕГРЮЛ по организации |
| [entrepreneur.md](entrepreneur.md) | `/entrepreneur` | Данные ЕГРИП по ИП |
| [person.md](person.md) | `/person` | Данные по физическому лицу |
| [finances.md](finances.md) | `/finances` | Финансовая отчётность |
| [legal-cases.md](legal-cases.md) | `/legal-cases` | Арбитражные дела |
| [contracts.md](contracts.md) | `/contracts` | Госзакупки (44-ФЗ, 223-ФЗ) |
| [inspections.md](inspections.md) | `/inspections` | Проверки |
| [bank.md](bank.md) | `/bank` | Банки по БИК |
| [timeline.md](timeline.md) | `/timeline` | История изменений (v2.4) |
| [fedresurs.md](fedresurs.md) | `/fedresurs` | Сообщения Федресурса (v2.4) |
| [bankruptcy-messages.md](bankruptcy-messages.md) | `/bankruptcy-messages` | Записи ЕФРСБ (v2.4) |

## История версий

| Версия | Дата | Изменения |
|--------|------|-----------|
| 2.4 | 04.02.2026 | Добавлены `/timeline`, `/fedresurs`, `/bankruptcy-messages`; в `/company` — СвязУчред; в `/search` — параметр `codes=all` |
| 2.3 | 07.07.2025 | В `/legal-cases` — фильтры `actual`, `active`, `claim_amount_from/to`; в `/company` — МассАдрес и Обрем |
| 2.2 | 23.09.2024 | Добавлен `balance` в `meta`; в `/company` и `/entrepreneur` — ЕФРСБ, ТекФНС, даты лицензий, уплата налогов |
| 2.1 | 07.08.2023 | Добавлен `/bank`; поиск по ОКПО в `/company` и `/entrepreneur`; санкции, товарные знаки, МСП |
| 2.0 | 16.10.2022 | Финальный релиз v2 |
