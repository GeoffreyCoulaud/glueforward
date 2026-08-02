# Contributing

This project uses [uv](https://docs.astral.sh/uv/) for dependency management. Install it first.

## Run the app locally (without Docker)

Install dependencies (httpx + the project, editable):

```sh
uv sync
```

Run glueforward with the required environment variables (see [README](README.md#environment-variables)):

```sh
GLUETUN_URL="http://gluetun:8000" \
GLUETUN_API_KEY="..." \
SERVICE_TYPE="qbittorrent" \
QBITTORRENT_URL="http://qbittorrent:8080" \
QBITTORRENT_USERNAME="admin" \
QBITTORRENT_PASSWORD="..." \
uv run glueforward
```

## Run the tests

Tests and linters live in the default `dev` group, installed by `uv sync`:

```sh
uv run pytest
```

Branch coverage must stay at 100%; the test run fails otherwise.

## Lint

```sh
uv run pylint glueforward
uv run pyright glueforward
```
