"""MCP-resources: статические markdown-документы поверх инструмента.

Каноничный контент лежит в `docs/`, `playbooks/` и `LEGAL.md` репозитория и:
- в production wheel пакуется через `[tool.hatch.build.targets.wheel.force-include]`
  в каталог `checko_mcp/_resources/`;
- в editable / dev-режиме читается напрямую из репозитория (fallback по `__file__`).
"""

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

import mcp_types as types

_PACKAGE_DATA = "checko_mcp._resources"


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    name: str
    title: str
    description: str
    file_name: str          # имя внутри package data
    repo_path: str          # относительный путь от корня репозитория (для dev fallback)


RESOURCES: list[ResourceSpec] = [
    ResourceSpec(
        uri="checko://docs/agent-guide",
        name="agent-guide",
        title="Agent Guide",
        description=(
            "Справочник для AI-агента: правила, поля ответов, "
            "приоритизированные факторы риска и анти-паттерны."
        ),
        file_name="agent-guide.md",
        repo_path="docs/instructions/agent-guide.md",
    ),
    ResourceSpec(
        uri="checko://docs/legal",
        name="legal",
        title="Правовые ограничения",
        description="Правовые основания использования (152-ФЗ, 149-ФЗ).",
        file_name="legal.md",
        repo_path="LEGAL.md",
    ),
    ResourceSpec(
        uri="checko://playbooks/audit/methodology",
        name="audit-methodology",
        title="Методология аудита физлица",
        description=(
            "Полная методология due-diligence физического лица — "
            "этапы, что искать, как интерпретировать."
        ),
        file_name="audit-methodology.md",
        repo_path="playbooks/audit/methodology.md",
    ),
    ResourceSpec(
        uri="checko://playbooks/audit/anomaly-checklist",
        name="audit-anomaly-checklist",
        title="Чеклист аномалий",
        description="Чеклист сигналов с описанием — что означают и как проверить.",
        file_name="audit-anomaly-checklist.md",
        repo_path="playbooks/audit/anomaly-checklist.md",
    ),
    ResourceSpec(
        uri="checko://playbooks/audit/template",
        name="audit-template",
        title="Шаблон отчёта аудита",
        description="Шаблон отчёта аудита физлица — копируется на каждого субъекта.",
        file_name="audit-template.md",
        repo_path="playbooks/audit/audit-template.md",
    ),
]


RESOURCES_BY_URI: dict[str, ResourceSpec] = {r.uri: r for r in RESOURCES}


def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri=spec.uri,  # type: ignore[arg-type]
            name=spec.name,
            title=spec.title,
            description=spec.description,
            mime_type="text/markdown",
        )
        for spec in RESOURCES
    ]


def read_resource_text(uri: str) -> str:
    """Возвращает markdown-контент ресурса по URI или поднимает FileNotFoundError."""
    spec = RESOURCES_BY_URI.get(uri)
    if spec is None:
        raise FileNotFoundError(f"Неизвестный ресурс: {uri}")
    return _load_text(spec)


def _load_text(spec: ResourceSpec) -> str:
    """Production: importlib.resources / dev fallback: путь в репозитории."""
    try:
        traversable = files(_PACKAGE_DATA).joinpath(spec.file_name)
        with as_file(traversable) as path:
            return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        repo_root = Path(__file__).resolve().parents[2]
        return (repo_root / spec.repo_path).read_text(encoding="utf-8")
