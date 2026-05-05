#!/usr/bin/env python3
"""End-to-end smoke-тест: запускает сервер через stdio и прогоняет основные сценарии.

Использование:
    python scripts/smoke.py                 # против локального python -m checko_mcp
    python scripts/smoke.py --docker        # против docker compose
    python scripts/smoke.py --no-api        # без реального вызова API

Требует CHECKO_API_KEY в окружении или .env, если не передан --no-api.
Реальный API-вызов выполняется только если задана `SMOKE_TEST_BIC` в окружении
(БИК действующего банка, 9 цифр). В коде идентификаторы не зашиты:
репозиторий не содержит настоящих ИНН/ОГРН/БИК — только синтетические placeholder'ы.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = 12
EXPECTED_RESOURCES = 5
EXPECTED_PROMPTS = 6

# Синтетические идентификаторы для проверки шаблонов prompts (не существуют в реестрах).
SYNTHETIC_INN_LEGAL = "1234567890"          # 10 цифр
SYNTHETIC_INN_PERSON = "123456789012"       # 12 цифр
SYNTHETIC_OGRN = "1234567890123"            # 13 цифр
SYNTHETIC_BIC = "123456789"                 # 9 цифр (только для format-валидации)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def _ok(name: str, detail: str = "") -> CheckResult:
    return CheckResult(name, True, detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, False, detail)


async def run_smoke(
    server_params: StdioServerParameters, *, real_bic: str | None
) -> list[CheckResult]:
    results: list[CheckResult] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            results.append(_ok("initialize", f"server: {init.serverInfo.name}"))

            # Tools
            tools = await session.list_tools()
            if len(tools.tools) == EXPECTED_TOOLS:
                results.append(_ok("list_tools", f"{len(tools.tools)} tools"))
            else:
                results.append(
                    _fail(
                        "list_tools",
                        f"ожидалось {EXPECTED_TOOLS}, получено {len(tools.tools)}",
                    )
                )

            # Resources
            resources = await session.list_resources()
            if len(resources.resources) == EXPECTED_RESOURCES:
                results.append(_ok("list_resources", f"{len(resources.resources)} resources"))
            else:
                results.append(
                    _fail(
                        "list_resources",
                        f"ожидалось {EXPECTED_RESOURCES}, получено {len(resources.resources)}",
                    )
                )

            for r in resources.resources:
                content = await session.read_resource(r.uri)
                texts = [c.text for c in content.contents if hasattr(c, "text")]
                size = sum(len(t) for t in texts)
                if size > 100:
                    results.append(_ok(f"read_resource[{r.name}]", f"{size} chars"))
                else:
                    results.append(
                        _fail(f"read_resource[{r.name}]", f"подозрительно мало: {size} chars")
                    )

            # Prompts
            prompts = await session.list_prompts()
            if len(prompts.prompts) == EXPECTED_PROMPTS:
                results.append(_ok("list_prompts", f"{len(prompts.prompts)} prompts"))
            else:
                results.append(
                    _fail(
                        "list_prompts",
                        f"ожидалось {EXPECTED_PROMPTS}, получено {len(prompts.prompts)}",
                    )
                )

            sample_args: dict[str, dict[str, str]] = {
                "check_counterparty": {
                    "query": "Тестовая Компания",
                    "purpose": "smoke-test",
                },
                "verify_bank_details": {
                    "inn": SYNTHETIC_INN_LEGAL,
                    "bic": SYNTHETIC_BIC,
                },
                "assess_bankruptcy_risk": {"inn": SYNTHETIC_INN_LEGAL},
                "audit_person": {"inn": SYNTHETIC_INN_PERSON},
                "evaluate_tender_participant": {"query": "ООО Тестовый Поставщик"},
                "analyze_finances": {"ogrn_or_inn": SYNTHETIC_OGRN, "years": "5"},
            }

            for p in prompts.prompts:
                args = sample_args.get(p.name, {})
                try:
                    result = await session.get_prompt(p.name, args)
                    text = result.messages[0].content.text if result.messages else ""
                    if len(text) > 200:
                        results.append(_ok(f"get_prompt[{p.name}]", f"{len(text)} chars"))
                    else:
                        results.append(
                            _fail(
                                f"get_prompt[{p.name}]",
                                f"подозрительно мало: {len(text)} chars",
                            )
                        )
                except Exception as exc:
                    results.append(_fail(f"get_prompt[{p.name}]", str(exc)))

            # Tool invocation: error path (валидация формата — без реального API)
            bad = await session.call_tool("get_bank", {"bic": "abc"})
            text = bad.content[0].text if bad.content else ""
            if "должен содержать ровно 9 цифр" in text:
                results.append(_ok("call_tool[get_bank: invalid bic → ValidationError]", text[:80]))
            else:
                results.append(
                    _fail(
                        "call_tool[get_bank: invalid bic]",
                        f"неожиданный ответ: {text[:200]}",
                    )
                )

            # Real API call (только если задан SMOKE_TEST_BIC)
            if real_bic:
                real = await session.call_tool("get_bank", {"bic": real_bic})
                if real.isError:
                    results.append(
                        _fail(
                            f"call_tool[get_bank(SMOKE_TEST_BIC=…{real_bic[-4:]})]",
                            f"isError: {real.content[0].text if real.content else '?'}",
                        )
                    )
                else:
                    text = real.content[0].text if real.content else ""
                    try:
                        data = json.loads(text)
                        meta = data.get("meta", {})
                        bank_name = (data.get("data") or {}).get("Наим", "—")
                        balance = meta.get("balance")
                        results.append(
                            _ok(
                                f"call_tool[get_bank(SMOKE_TEST_BIC=…{real_bic[-4:]})]",
                                f"банк='{bank_name[:50]}', balance={balance}",
                            )
                        )
                    except json.JSONDecodeError as exc:
                        results.append(
                            _fail(
                                f"call_tool[get_bank(SMOKE_TEST_BIC=…{real_bic[-4:]})]",
                                f"не JSON: {exc}",
                            )
                        )

    return results


def print_results(results: list[CheckResult]) -> int:
    failed = 0
    for r in results:
        marker = "PASS" if r.ok else "FAIL"
        print(f"  [{marker}] {r.name:62s} {r.detail}")
        if not r.ok:
            failed += 1
    print()
    print(f"=> {len(results) - failed}/{len(results)} checks passed")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", action="store_true", help="Запустить против docker compose")
    parser.add_argument("--no-api", action="store_true", help="Пропустить реальный вызов API")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("CHECKO_API_KEY", "").strip()
    real_bic_raw = os.environ.get("SMOKE_TEST_BIC", "").strip()

    real_bic: str | None = None
    if not args.no_api:
        if not api_key:
            print("WARN: CHECKO_API_KEY не задан — реальный вызов API будет пропущен.")
        elif not real_bic_raw:
            print(
                "WARN: SMOKE_TEST_BIC не задан — реальный вызов API будет пропущен.\n"
                "      Чтобы включить, локально задайте в .env БИК действующего банка (9 цифр)."
            )
        elif not (real_bic_raw.isdigit() and len(real_bic_raw) == 9):
            print(
                f"WARN: SMOKE_TEST_BIC='{real_bic_raw}' — нужен формат 9 цифр; пропускаем."
            )
        else:
            real_bic = real_bic_raw

    if args.docker:
        compose_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.pardir, "docker-compose.yml")
        )
        server_params = StdioServerParameters(
            command="docker",
            args=["compose", "-f", compose_path, "run", "--rm", "-T", "checko-mcp"],
        )
        target = "Docker"
    else:
        env = {"CHECKO_API_KEY": api_key} if api_key else None
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "checko_mcp"],
            env=env,
        )
        target = "Local (python -m checko_mcp)"

    print(f"== Smoke-тест: {target} ==")
    print(f"== Реальный API вызов: {'да (через SMOKE_TEST_BIC)' if real_bic else 'нет'} ==")
    print()

    try:
        results = asyncio.run(run_smoke(server_params, real_bic=real_bic))
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    return print_results(results)


if __name__ == "__main__":
    sys.exit(main())
