"""Shared pytest fixtures for glueforward tests."""

from collections.abc import Callable

import httpx
import pytest

# Distinctive enough to be searched for in the logs.
GLUETUN_API_KEY = "gluetun-api-key-3f9a2c"
QBITTORRENT_PASSWORD = "qbittorrent-password-7d1e04"

# Full, valid environment for a qBittorrent deployment.
VALID_ENVIRONMENT = {
    "GLUETUN_URL": "http://gluetun",
    "GLUETUN_API_KEY": GLUETUN_API_KEY,
    "SERVICE_TYPE": "qbittorrent",
    "QBITTORRENT_URL": "http://qbittorrent",
    "QBITTORRENT_USERNAME": "user",
    "QBITTORRENT_PASSWORD": QBITTORRENT_PASSWORD,
}


@pytest.fixture
def valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start from an environment a real deployment would work with."""
    for name, value in VALID_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


class EndOfTest(Exception):
    """Stands in for an unretryable error, and ends run()'s endless loop."""


class FakeClock:
    """A clock the test moves by hand, and which records what it waited on."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.slept.append(duration)
        self.now += duration


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def mock_httpx(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable], None]:
    """Patch ``httpx.Client`` so every client created during the test drives a
    real ``httpx.Client`` backed by an ``httpx.MockTransport``.

    The production code builds its own ``httpx.Client`` internally; this fixture
    intercepts that construction and injects a mock transport, letting each test
    script responses (and errors) deterministically without touching the network.

    Usage::

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"port": 12345})

        def test_something(mock_httpx):
            mock_httpx(handler)
            ...
    """
    real_client = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        transport = httpx.MockTransport(handler)

        def factory(*args: object, **kwargs: object) -> httpx.Client:
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", factory)

    return install
