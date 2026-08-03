"""Определение вида идентификатора и выбор эндпоинта.

Агент постоянно ошибается именно здесь: у Checko пять разных идентификаторов,
и какой метод вызывать, определяется числом цифр. Модель угадывает это плохо —
особенно для 12 цифр, где ИНН может принадлежать и предпринимателю, и физлицу
без ИП. Поэтому маршрутизация делается кодом, детерминированно.

    8  цифр — ОКПО организации
    9  цифр — БИК банка (либо белорусский УНП, которого в API нет)
    10 цифр — ИНН организации
    12 цифр — ИНН физлица: может быть ИП, может быть физлицо без ИП
    13 цифр — ОГРН организации
    15 цифр — ОГРНИП предпринимателя
"""

from dataclasses import dataclass

from ._validation import ValidationError

ORG = "org"
ENTREPRENEUR = "entrepreneur"
PERSON = "person"
BANK = "bank"

KINDS = (ORG, ENTREPRENEUR, PERSON, BANK)


@dataclass(frozen=True)
class Route:
    """Куда идти с этим идентификатором."""

    kind: str
    endpoint: str
    params: dict[str, str]
    # Второй вариант, если первый вернул пустой ответ.
    fallback: "Route | None" = None
    note: str | None = None


def normalize(value: object) -> str:
    return str(value or "").strip().replace(" ", "").replace("-", "")


def classify(identifier: str) -> Route:
    """Определить маршрут по идентификатору. Поднимает ValidationError, если не понял."""
    clean = normalize(identifier)

    if not clean:
        raise ValidationError("Не указан идентификатор.")
    if not clean.isdigit():
        raise ValidationError(
            f"Идентификатор должен состоять только из цифр (получено: '{identifier}'). "
            "Если это наименование или ФИО — используйте инструмент `resolve`."
        )

    length = len(clean)

    if length == 13:
        return Route(ORG, "/company", {"ogrn": clean})
    if length == 15:
        return Route(ENTREPRENEUR, "/entrepreneur", {"ogrn": clean})
    if length == 10:
        return Route(ORG, "/company", {"inn": clean})
    if length == 12:
        # Сначала ЕГРИП: если предприниматель есть, его карточка информативнее.
        # Если нет — физлицо и его связи.
        return Route(
            ENTREPRENEUR,
            "/entrepreneur",
            {"inn": clean},
            fallback=Route(PERSON, "/person", {"inn": clean}),
            note=(
                "ИНН из 12 цифр принадлежит физическому лицу. Если действующего ИП нет, "
                "запрос уходит в /person — это персональные данные, и их обработка "
                "требует законного основания (152-ФЗ, см. checko://docs/legal)."
            ),
        )
    if length == 8:
        return Route(
            ORG,
            "/company",
            {"okpo": clean},
            fallback=Route(ENTREPRENEUR, "/entrepreneur", {"okpo": clean}),
        )
    if length == 9:
        return Route(
            BANK,
            "/bank",
            {"bic": clean},
            note=(
                "9 цифр — это БИК банка. Столько же цифр у белорусского УНП, "
                "но белорусских данных в API нет: если это УНП, ответ будет пустым."
            ),
        )

    raise ValidationError(
        f"Не удалось определить вид идентификатора по {length} цифрам: '{clean}'. "
        "Ожидается 8 (ОКПО), 9 (БИК), 10 (ИНН юрлица), 12 (ИНН физлица), "
        "13 (ОГРН) или 15 (ОГРНИП) цифр."
    )


def route_for_kind(identifier: str, kind: str) -> Route:
    """Маршрут с явно заданным видом субъекта — обходит автоопределение."""
    clean = normalize(identifier)
    if not clean.isdigit():
        raise ValidationError(f"Идентификатор должен состоять только из цифр: '{identifier}'.")

    if kind == PERSON:
        if len(clean) != 12:
            raise ValidationError(
                f"ИНН физлица содержит 12 цифр (получено {len(clean)}): '{clean}'."
            )
        return Route(PERSON, "/person", {"inn": clean})

    if kind == BANK:
        if len(clean) != 9:
            raise ValidationError(f"БИК содержит 9 цифр (получено {len(clean)}): '{clean}'.")
        return Route(BANK, "/bank", {"bic": clean})

    if kind == ENTREPRENEUR:
        if len(clean) == 15:
            return Route(ENTREPRENEUR, "/entrepreneur", {"ogrn": clean})
        if len(clean) == 12:
            return Route(ENTREPRENEUR, "/entrepreneur", {"inn": clean})
        if len(clean) == 8:
            return Route(ENTREPRENEUR, "/entrepreneur", {"okpo": clean})
        raise ValidationError(
            f"Для ИП ожидается ОГРНИП (15), ИНН (12) или ОКПО (8) цифр, получено {len(clean)}."
        )

    if kind == ORG:
        if len(clean) == 13:
            return Route(ORG, "/company", {"ogrn": clean})
        if len(clean) == 10:
            return Route(ORG, "/company", {"inn": clean})
        if len(clean) == 8:
            return Route(ORG, "/company", {"okpo": clean})
        raise ValidationError(
            f"Для организации ожидается ОГРН (13), ИНН (10) или ОКПО (8) цифр, "
            f"получено {len(clean)}."
        )

    raise ValidationError(f"Неизвестный вид субъекта: '{kind}'. Допустимо: {', '.join(KINDS)}.")


def subject_params(identifier: str) -> dict[str, str]:
    """Параметры для методов, принимающих и ОГРН, и ИНН любого субъекта."""
    clean = normalize(identifier)
    if not clean.isdigit():
        raise ValidationError(f"Идентификатор должен состоять только из цифр: '{identifier}'.")
    if len(clean) in (13, 15):
        return {"ogrn": clean}
    if len(clean) in (10, 12):
        return {"inn": clean}
    raise ValidationError(
        f"Ожидается ОГРН (13), ОГРНИП (15), ИНН юрлица (10) или ИНН физлица (12) цифр, "
        f"получено {len(clean)}: '{clean}'."
    )
