FROM python:3.12-slim-trixie@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1
ENV UV_PYTHON_DOWNLOADS=0
# The BuildKit cache lives on a different filesystem than /app, so hardlinks
# fail and uv falls back to copying. Make that explicit to silence the warning.
ENV UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, in a cached layer independent of source changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Install the project itself into the venv, non-editable so it ships inside .venv
# (along with the `glueforward` console script) and no source is needed at runtime.
COPY pyproject.toml uv.lock README.md ./
COPY glueforward ./glueforward

# No uv cache mount here: with a constant name+version it would serve a stale
# `glueforward` wheel when only source files change. Building fresh is cheap
# (deps are already in the venv) and guarantees the package matches the source.
RUN uv sync --locked --no-editable

FROM python:3.12-slim-trixie@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

WORKDIR /app
# Only the venv: it carries the installed package and the `glueforward` entry point.
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENTRYPOINT [ "/app/.venv/bin/glueforward" ]
