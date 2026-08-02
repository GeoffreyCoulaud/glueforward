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

## Run the end-to-end tests

Unlike the tests above, these spin up real Docker containers, gluetun connected to a real ProtonVPN account, a real qBittorrent, and glueforward built straight from the repository's `Dockerfile`, and assert the app's behavior purely from the outside, through the same public APIs a real deployment would use.

They require:

- Docker, with access to `/dev/net/tun` (the default on Linux hosts)
- A ProtonVPN account with [port forwarding](https://protonvpn.com/support/wireguard-configurations/) enabled, and its WireGuard private key

Provide the private key as a `WIREGUARD_PRIVATE_KEY` environment variable, either exported in your shell or in a `.env.e2e.local` file at the repository root (gitignored, loaded automatically). **Never commit this key, or paste it anywhere it could be logged** (chat, issue, CI log, etc.).

```sh
# .env.e2e.local
WIREGUARD_PRIVATE_KEY=...
# Optional, defaults to Netherlands. Pick a country your plan can port-forward from.
SERVER_COUNTRIES=...
```

Then:

```sh
uv run pytest glueforward/tests/end_to_end -o addopts=""
```

The `-o addopts=""` resets the coverage flags from `pyproject.toml`: they target `glueforward.main` in-process and don't make sense here, since the code under test runs in a separate container.

Without `WIREGUARD_PRIVATE_KEY` set, these tests are skipped automatically, and a plain `uv run pytest` never runs them (they're outside `testpaths`). Expect a real run to take a minute or two: it builds an image and negotiates a real VPN connection.

## Lint

```sh
uv run pylint glueforward/main
uv run pyright glueforward/main
```
