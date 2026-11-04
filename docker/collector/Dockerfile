# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies get their own layer so code changes don't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --extra collector

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY collector ./collector
COPY spark_jobs ./spark_jobs
COPY quality ./quality
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra collector


FROM python:3.12-slim

RUN useradd --create-home --uid 10001 collector
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER collector
ENTRYPOINT ["python", "-m", "collector"]
