"""HTTP-клиент для Checko.ru API v2."""

import os
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.checko.ru/v2"
DEFAULT_TIMEOUT = 30.0
MAX_ERROR_BODY_LENGTH = 500


class CheckoAPIError(Exception):
    """Ошибка от Checko API."""


class CheckoClient:
    """Async HTTP-клиент для Checko.ru API v2.

    Использует переменную окружения CHECKO_API_KEY для авторизации.
    Базовый URL может быть переопределён через CHECKO_BASE_URL (полезно для тестов).
    Один экземпляр держит постоянный httpx.AsyncClient — закрывается через aclose().
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        load_dotenv()
        self._api_key = os.environ.get("CHECKO_API_KEY", "").strip()
        if not self._api_key:
            raise CheckoAPIError(
                "Не задан API-ключ. Установите переменную окружения CHECKO_API_KEY."
            )
        self._base_url = os.environ.get("CHECKO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self._timeout = float(os.environ.get("CHECKO_TIMEOUT", DEFAULT_TIMEOUT))
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        """Выполнить GET-запрос к Checko API.

        Args:
            endpoint: Путь эндпоинта, например '/company'.
            **params: Query-параметры запроса (без key — он добавляется автоматически).

        Returns:
            Полный JSON-ответ в виде словаря.

        Raises:
            CheckoAPIError: Если API вернул статус ошибки или произошла HTTP-ошибка.
        """
        clean_params: dict[str, Any] = {k: v for k, v in params.items() if v is not None}
        clean_params["key"] = self._api_key

        try:
            response = await self._http.get(endpoint, params=clean_params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:MAX_ERROR_BODY_LENGTH]
            raise CheckoAPIError(f"HTTP {exc.response.status_code}: {body}") from exc
        except httpx.RequestError as exc:
            raise CheckoAPIError(f"Ошибка соединения с Checko API: {exc}") from exc

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise CheckoAPIError(f"Некорректный JSON-ответ от Checko API: {exc}") from exc

        meta = data.get("meta", {})
        if meta.get("status") == "error":
            message = meta.get("message", "Неизвестная ошибка Checko API")
            raise CheckoAPIError(message)

        return data
