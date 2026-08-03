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

Unlike the tests above, these spin up real Docker containers, a real qBittorrent, and glueforward built straight from the repository's `Dockerfile`, and assert the app's behavior purely from the outside, through the same public APIs a real deployment would use.

Every container is created per test, so tests share nothing, may run in any order, and may run in parallel with `-n`:

```sh
uv run pytest glueforward/tests/end_to_end -o addopts="" -n 4
```

They come in two families:

- Most of them need no VPN tunnel, and therefore no secret. gluetun's control server is stood in for by a small HTTP server the test drives, which is the only way to choose a forwarded port and change it on command. Run them with `-m "not vpn"`.
- A few pin glueforward against gluetun's real port forwarding, and need a real ProtonVPN connection. They are marked `vpn`.

The `vpn` ones require:

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

Without `WIREGUARD_PRIVATE_KEY` set, the `vpn` tests are skipped automatically, and a plain `uv run pytest` never runs any of these (they're outside `testpaths`). One WireGuard key is one VPN session, so the `vpn` tests hold a lock and run one at a time however you invoke them. Expect them to take about forty seconds each: they build an image and negotiate a real VPN connection.

In CI they are split accordingly. The tests needing no key run in `check.yml`, on every pull request, forks included. The `vpn` ones run in `end-to-end-tests.yml`, behind the approval described below.

## Approving end-to-end tests on a fork pull request

The end-to-end tests need the real ProtonVPN key from above, so on a pull request from a fork they wait for a maintainer to approve the run (`main-pr.yml`, gated by the `e2e-fork-approval` environment). Dependabot's pull requests wait there too: they come from a branch of this repository, but nobody has read them yet when they open. Pull requests from a branch a person pushed run them unattended.

That approval is the *only* barrier between the pull request's code and the key. Before clicking Approve, read the whole diff rather than just the application code. The `Dockerfile`, `conftest.py`, `pyproject.toml` and `uv.lock` all run with the secret in scope too.

## Lint

```sh
uv run pylint glueforward
uv run pyright glueforward
docker run --rm -v "$(pwd):/repo" --workdir /repo rhysd/actionlint:1.7.12
```

Both linters cover the tests as well as the application.
