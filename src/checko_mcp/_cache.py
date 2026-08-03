"""Кэш ответов Checko API с временем жизни.

Каждый вызов инструмента — платный запрос: бесплатный тариф даёт 100 запросов
в сутки, дальше 0,10–0,15 руб. за запрос. Агенты же переспрашивают одно и то же
постоянно: сначала карточку организации, потом отчёт, который снова берёт карточку,
потом уточнение по тому же ОГРН. Без кэша каждый такой повтор оплачивается заново.

Кэш живёт в памяти процесса и очищается вместе с ним. Ошибки не кэшируются:
временный сбой не должен закрепиться на всё время жизни сервера.
"""

import time
from typing import Any

DEFAULT_TTL = 900.0
MAX_ENTRIES = 256


def make_key(endpoint: str, params: dict[str, Any]) -> tuple:
    """Ключ, не зависящий от порядка параметров. API-ключ в него не входит."""
    return (endpoint, tuple(sorted((k, str(v)) for k, v in params.items() if k != "key")))


class ResponseCache:
    """Простой TTL-кэш с ограничением по числу записей."""

    def __init__(self, ttl: float = DEFAULT_TTL, max_entries: int = MAX_ENTRIES) -> None:
        self._ttl = ttl
        self._max_entries = max_entries
        self._entries: dict[tuple, tuple[float, dict[str, Any]]] = {}
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: tuple) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        stored_at, payload = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._entries[key]
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def put(self, key: tuple, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        if len(self._entries) >= self._max_entries:
            # Вытесняем самую старую запись — точный LRU здесь не нужен.
            oldest = min(self._entries, key=lambda k: self._entries[k][0])
            del self._entries[oldest]
        self._entries[key] = (time.monotonic(), payload)

    def clear(self) -> None:
        self._entries.clear()
