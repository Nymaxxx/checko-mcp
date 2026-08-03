"""HTTP-клиент для Checko.ru API v2."""

import asyncio
import os
from typing import Any

import httpx2 as httpx
from dotenv import load_dotenv

from . import __version__
from ._cache import DEFAULT_TTL, ResponseCache, make_key

DEFAULT_BASE_URL = "https://api.checko.ru/v2"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.5
MAX_ERROR_BODY_LENGTH = 500
MAX_BACKOFF = 8.0

# Ошибки, которые имеет смысл повторить: превышение частоты запросов
# и временные сбои на стороне сервиса.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class CheckoAPIError(Exception):
    """Ошибка от Checko API."""


def _describe(exc: Exception) -> str:
    """Непустое описание исключения.

    У части сетевых ошибок httpx `str(exc)` пуст (например, при сбое DNS),
    и агент получал сообщение «Ошибка соединения с Checko API: » без причины.
    """
    text = str(exc).strip()
    return text or exc.__class__.__name__


class CheckoClient:
    """Async HTTP-клиент для Checko.ru API v2.

    API-ключ берётся из переменной окружения `CHECKO_API_KEY` и передаётся
    query-параметром `key` — так требует Checko. Базовый URL переопределяется
    через `CHECKO_BASE_URL`, таймаут — через `CHECKO_TIMEOUT`, число повторов —
    через `CHECKO_RETRIES`.

    Один экземпляр держит постоянный httpx.AsyncClient; закрывается через `aclose()`.
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        backoff: float | None = None,
    ) -> None:
        load_dotenv()
        self._api_key = os.environ.get("CHECKO_API_KEY", "").strip()
        if not self._api_key:
            raise CheckoAPIError(
                "Не задан API-ключ. Установите переменную окружения CHECKO_API_KEY. "
                "Ключ выдаётся в личном кабинете: https://checko.ru/user/account/api"
            )
        self._base_url = os.environ.get("CHECKO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self._timeout = float(os.environ.get("CHECKO_TIMEOUT", DEFAULT_TIMEOUT))
        self._retries = max(1, int(os.environ.get("CHECKO_RETRIES", DEFAULT_RETRIES)))
        self._backoff = DEFAULT_BACKOFF if backoff is None else backoff
        self._last_balance: float | None = None
        self._billed_requests = 0
        self.cache = ResponseCache(float(os.environ.get("CHECKO_CACHE_TTL", DEFAULT_TTL)))
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=transport,
            headers={"User-Agent": f"checko-mcp/{__version__}"},
        )

    @property
    def last_balance(self) -> float | None:
        """Баланс из `meta.balance` последнего успешного ответа, руб."""
        return self._last_balance

    @property
    def billed_requests(self) -> int:
        """Сколько запросов реально ушло в API (без отданных из кэша)."""
        return self._billed_requests

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        """Выполнить GET-запрос к Checko API.

        Args:
            endpoint: Путь эндпоинта, например '/company'.
            **params: Query-параметры (без `key` — он добавляется автоматически).

        Returns:
            Полный JSON-ответ в виде словаря.

        Raises:
            CheckoAPIError: API вернул статус ошибки либо запрос не удался.
        """
        clean_params: dict[str, Any] = {k: v for k, v in params.items() if v is not None}

        cache_key = make_key(endpoint, clean_params)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        clean_params["key"] = self._api_key
        response = await self._request_with_retry(endpoint, clean_params)
        self._billed_requests += 1

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise CheckoAPIError(f"Некорректный JSON-ответ от Checko API: {exc}") from exc

        meta = data.get("meta") or {}
        if isinstance(meta, dict):
            balance = meta.get("balance")
            if isinstance(balance, (int, float)):
                self._last_balance = float(balance)
            if meta.get("status") == "error":
                # Ошибки не кэшируем: временный сбой не должен закрепиться на весь TTL.
                raise CheckoAPIError(meta.get("message") or "Неизвестная ошибка Checko API")

        self.cache.put(cache_key, data)
        return data

    async def _request_with_retry(
        self, endpoint: str, params: dict[str, Any]
    ) -> httpx.Response:
        last_error: str = "запрос не выполнен"

        for attempt in range(self._retries):
            try:
                response = await self._http.get(endpoint, params=params)
            except httpx.RequestError as exc:
                last_error = f"Ошибка соединения с Checko API: {_describe(exc)}"
            else:
                if response.status_code not in _RETRY_STATUSES:
                    if response.is_error:
                        body = (response.text or "")[:MAX_ERROR_BODY_LENGTH]
                        raise CheckoAPIError(f"HTTP {response.status_code}: {body}")
                    return response

                body = (response.text or "")[:MAX_ERROR_BODY_LENGTH]
                last_error = f"HTTP {response.status_code}: {body}"
                if response.status_code == 429:
                    last_error = (
                        "Превышен лимит запросов Checko API (HTTP 429). "
                        "Бесплатный тариф — 100 запросов в сутки."
                    )
                await self._sleep_before_retry(attempt, response)
                continue

            await self._sleep_before_retry(attempt, None)

        raise CheckoAPIError(f"{last_error} (попыток: {self._retries})")

    async def _sleep_before_retry(self, attempt: int, response: httpx.Response | None) -> None:
        # После последней попытки пауза бессмысленна — ошибка отдаётся сразу.
        if attempt >= self._retries - 1 or self._backoff <= 0:
            return
        delay = min(self._backoff * (2**attempt), MAX_BACKOFF)
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.strip().isdigit():
                delay = min(float(retry_after.strip()), MAX_BACKOFF)
        await asyncio.sleep(delay)
