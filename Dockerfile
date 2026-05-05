FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Канонические markdown-ресурсы нужны на этапе сборки wheel —
# hatchling force-include упакует их внутрь пакета.
COPY pyproject.toml README.md LEGAL.md ./
COPY src/ ./src/
COPY docs/ ./docs/
COPY playbooks/ ./playbooks/

RUN pip install --prefix=/install .


FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.13/site-packages"

COPY --from=builder /install /install

RUN useradd --system --uid 1000 --create-home --shell /bin/bash app
USER app
WORKDIR /home/app

CMD ["python", "-m", "checko_mcp"]
