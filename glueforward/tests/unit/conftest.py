"""Shared pytest fixtures for glueforward tests."""

from collections.abc import Callable

import httpx
import pytest


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
