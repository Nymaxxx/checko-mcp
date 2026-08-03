"""Тесты кэша ответов.

Каждый запрос платный: 100 в сутки бесплатно, дальше 0,10–0,15 руб. Каскадный
отчёт тратит 5–6 запросов, и если агент после отчёта уточняет детали по тому же
субъекту, без кэша всё оплачивается заново.
"""

import httpx2 as httpx
import pytest

from checko_mcp._cache import ResponseCache, make_key
from checko_mcp.client import CheckoAPIError


class TestMakeKey:
    def test_parameter_order_does_not_matter(self) -> None:
        assert make_key("/company", {"ogrn": "1", "source": "true"}) == make_key(
            "/company", {"source": "true", "ogrn": "1"}
        )

    def test_api_key_is_excluded(self) -> None:
        """Иначе смена ключа сбрасывала бы кэш, а сам ключ лежал бы в структуре."""
        assert make_key("/company", {"ogrn": "1", "key": "secret"}) == make_key(
            "/company", {"ogrn": "1"}
        )

    def test_different_endpoints_differ(self) -> None:
        assert make_key("/company", {"inn": "1"}) != make_key("/finances", {"inn": "1"})


class TestResponseCache:
    def test_stores_and_returns(self) -> None:
        cache = ResponseCache(ttl=60)
        key = make_key("/company", {"inn": "1"})
        cache.put(key, {"data": 1})
        assert cache.get(key) == {"data": 1}
        assert (cache.hits, cache.misses) == (1, 0)

    def test_miss_is_counted(self) -> None:
        cache = ResponseCache(ttl=60)
        assert cache.get(make_key("/company", {"inn": "1"})) is None
        assert cache.misses == 1

    def test_zero_ttl_disables_cache(self) -> None:
        cache = ResponseCache(ttl=0)
        key = make_key("/company", {"inn": "1"})
        cache.put(key, {"data": 1})
        assert cache.get(key) is None
        assert cache.enabled is False

    def test_expired_entry_is_dropped(self) -> None:
        cache = ResponseCache(ttl=-1)
        assert cache.enabled is False

    def test_evicts_when_full(self) -> None:
        cache = ResponseCache(ttl=60, max_entries=2)
        for i in range(3):
            cache.put(make_key("/company", {"inn": str(i)}), {"n": i})
        assert cache.get(make_key("/company", {"inn": "0"})) is None
        assert cache.get(make_key("/company", {"inn": "2"})) == {"n": 2}

    def test_clear_empties_cache(self) -> None:
        cache = ResponseCache(ttl=60)
        key = make_key("/company", {"inn": "1"})
        cache.put(key, {"data": 1})
        cache.clear()
        assert cache.get(key) is None


class TestClientCaching:
    @pytest.fixture(autouse=True)
    def _enable_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHECKO_CACHE_TTL", "300")

    async def test_repeated_request_is_not_billed_twice(self, make_client) -> None:
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"data": {"a": 1}, "meta": {"status": "ok"}})

        client = make_client(handler)
        first = await client.get("/company", inn="1234567890")
        second = await client.get("/company", inn="1234567890")

        assert first["data"] == second["data"]
        assert calls["n"] == 1
        assert client.billed_requests == 1

    async def test_different_params_are_cached_separately(self, make_client) -> None:
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"data": {}, "meta": {"status": "ok"}})

        client = make_client(handler)
        await client.get("/company", inn="1234567890")
        await client.get("/company", inn="9999999999")
        assert calls["n"] == 2

    async def test_cached_answer_drops_stale_quota_counter(self, make_client) -> None:
        """Счётчик запросов из кэша устарел, и агент следит по нему за квотой.

        Найдено на живом API: `resolve` показал 51, каскадный отчёт истратил
        ещё 6, а следующий вызов отдал 54 — счётчик уменьшился. Агент, которому
        предписано предупреждать у 100, получал заниженную оценку расхода.
        """

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": {"a": 1}, "meta": {"status": "ok", "today_request_count": 51}},
            )

        client = make_client(handler)
        fresh = await client.get("/company", inn="1234567890")
        cached = await client.get("/company", inn="1234567890")

        assert fresh["meta"]["today_request_count"] == 51
        assert "today_request_count" not in cached["meta"]
        assert cached["meta"]["из_кэша"] is True
        assert "из_кэша" not in fresh["meta"]

    async def test_marking_cache_hit_does_not_corrupt_the_entry(self, make_client) -> None:
        """Пометка не должна править запись в кэше: следующий читатель ждёт её целой."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": {"a": 1}, "meta": {"status": "ok", "today_request_count": 7}},
            )

        client = make_client(handler)
        await client.get("/company", inn="1234567890")
        first_hit = await client.get("/company", inn="1234567890")
        second_hit = await client.get("/company", inn="1234567890")

        assert first_hit["meta"] == second_hit["meta"]
        assert client.billed_requests == 1

    async def test_errors_are_not_cached(self, make_client) -> None:
        """Временный сбой не должен закрепиться на всё время жизни кэша."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200, json={"meta": {"status": "error", "message": "сбой"}}
                )
            return httpx.Response(200, json={"data": {"a": 1}, "meta": {"status": "ok"}})

        client = make_client(handler)
        with pytest.raises(CheckoAPIError):
            await client.get("/company", inn="1234567890")
        result = await client.get("/company", inn="1234567890")

        assert result["data"] == {"a": 1}
        assert calls["n"] == 2

    async def test_ttl_zero_disables_client_cache(self, monkeypatch, make_client) -> None:
        monkeypatch.setenv("CHECKO_CACHE_TTL", "0")
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"data": {}, "meta": {"status": "ok"}})

        client = make_client(handler)
        await client.get("/company", inn="1234567890")
        await client.get("/company", inn="1234567890")
        assert calls["n"] == 2

    async def test_billed_counter_ignores_cache_hits(self, make_client) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {}, "meta": {"status": "ok"}})

        client = make_client(handler)
        for _ in range(5):
            await client.get("/company", inn="1234567890")
        assert client.billed_requests == 1


class TestCascadeReusesCache:
    @pytest.fixture(autouse=True)
    def _enable_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHECKO_CACHE_TTL", "300")

    async def test_second_report_costs_nothing(self, make_client) -> None:
        """Повторный отчёт по тому же субъекту не должен оплачиваться заново."""
        from checko_mcp._reports import due_diligence_report

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(
                200,
                json={
                    "data": {"ОГРН": "1234567890123", "Статус": {"Наим": "Действует"}},
                    "meta": {"status": "ok"},
                },
            )

        client = make_client(handler)
        first = await due_diligence_report(client, {"identifier": "1234567890123"}, "compact")
        after_first = calls["n"]
        second = await due_diligence_report(client, {"identifier": "1234567890123"}, "compact")

        assert first["запросов_в_api"] == after_first
        assert second["запросов_в_api"] == 0
        assert calls["n"] == after_first
