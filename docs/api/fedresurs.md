# /fedresurs — Сообщения Федресурса (v2.4)

Сообщения Федресурса (ЕФРСФДЮЛ — Единый федеральный реестр сведений о фактах деятельности юридических лиц) по организациям и ИП. Добавлен в версии 2.4 (февраль 2026).

## Запрос

```
GET https://api.checko.ru/v2/fedresurs?key=API_KEY&inn={ИНН}
GET https://api.checko.ru/v2/fedresurs?key=API_KEY&ogrn={ОГРН}&role=publisher
```

## Параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|:------------:|----------|
| `key` | string | да | API-ключ |
| `ogrn` | string | один из | ОГРН организации или ОГРНИП ИП |
| `inn` | string | один из | ИНН организации или ИП |
| `type` | string | нет | Тип сообщения (например, `CreditorIntentionGoToCourt`) |
| `role` | string | нет | `all` (по умолчанию) или `publisher` (только публикатор) |
| `date_from` | string | нет | Дата публикации от (YYYY-MM-DD) |
| `date_to` | string | нет | Дата публикации до (YYYY-MM-DD) |
| `limit` | integer | нет | Записей на страницу (макс. 100) |
| `page` | integer | нет | Номер страницы |
| `sort` | string | нет | `date` или `-date` |

## Примеры

```
GET https://api.checko.ru/v2/fedresurs?key=API_KEY&inn={ИНН}
GET https://api.checko.ru/v2/fedresurs?key=API_KEY&ogrn={ОГРН}&role=publisher
GET https://api.checko.ru/v2/fedresurs?key=API_KEY&inn={ИНН}&type=CreditorIntentionGoToCourt&date_from=2025-01-01
```

## Формат ответа

```json
{
  "company": {
    "ОГРН": "...", "ИНН": "...", "НаимСокр": "...", "Статус": "Действующая"
  },
  "entrepreneur": null,
  "data": {
    "ЗапВсего": 8,
    "СтрВсего": 1,
    "СтрТекущ": 1,
    "Записи": [
      {
        "GUID": "550e8400-e29b-41d4-a716-446655440000",
        "URL": "https://fedresurs.ru/Message/...",
        "Дата": "2025-03-15",
        "Тип": "CreditorIntentionGoToCourt",
        "ТипНаим": "Намерение кредитора обратиться в суд с заявлением о банкротстве",
        "Публикатор": "XXXXXXXXXXXXX",
        "Участники": [ "XXXXXXXXXX", "YYYYYYYYYYYYY" ]
      }
    ]
  },
  "meta": { "status": "ok", "today_request_count": 1, "balance": 1000 }
}
```

## Поля ответа

| Поле | Описание |
|------|----------|
| `data.ЗапВсего` | Общее количество сообщений |
| `data.Записи[].GUID` | GUID сообщения |
| `data.Записи[].URL` | Ссылка на страницу Федресурса |
| `data.Записи[].Дата` | Дата публикации |
| `data.Записи[].Тип` | Тип сообщения (код) |
| `data.Записи[].ТипНаим` | Описание типа сообщения |
| `data.Записи[].Публикатор` | ОГРН/ОГРНИП публикатора |
| `data.Записи[].Участники[]` | ОГРН или ИНН участников сообщения |

## Справочник типов сообщений

Полный перечень типов с расшифровкой: https://checko.ru/uploads/datasets/message_types.xlsx

Наиболее важные типы:

| Тип | Описание |
|-----|----------|
| `CreditorIntentionGoToCourt` | Намерение кредитора обратиться с заявлением о банкротстве |
| `BankruptcyIntroduced` | Введена процедура банкротства |
| `PledgeAgreement` | Уведомление о залоге |
| `LeaseAgreement` | Уведомление о лизинге |
| `LiquidationMessage` | Сообщение о ликвидации |
