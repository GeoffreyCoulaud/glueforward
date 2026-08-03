"""Unit tests for glueforward.gluetun."""

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import (
    GluetunAuthFailed,
    GluetunClient,
    GluetunNoForwardedPort,
    GluetunServerError,
    GluetunUnreachable,
)


@pytest.mark.parametrize(
    "error, is_retryable",
    [
        (GluetunUnreachable, True),
        (GluetunServerError, True),
        (GluetunNoForwardedPort, True),
        (GluetunAuthFailed, False),
    ],
)
def test_retry_policy(error, is_retryable):
    """A tunnel comes back on its own; a rejected API key never does."""
    assert issubclass(error, RetryableError) is is_retryable


def test_init_sets_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "secret"
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key="secret")
    assert client.get_forwarded_port() == 1


def test_init_without_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-API-Key" not in request.headers
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    assert client.get_forwarded_port() == 1


def test_get_forwarded_port_success(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": 50000})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    assert client.get_forwarded_port() == 50000


def test_get_forwarded_port_requests_the_control_server_endpoint(mock_httpx):
    """The endpoint is gluetun's, so nothing in this repository can vouch for it."""
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    GluetunClient(url="http://gluetun", api_key=None).get_forwarded_port()

    assert seen == [("GET", "/v1/portforward")]


def test_get_forwarded_port_not_forwarded_yet(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": 0})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunNoForwardedPort):
        client.get_forwarded_port()


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_timeout", "connect_timeout"],
)
def test_get_forwarded_port_unreachable(mock_httpx, exception):
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception("boom")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunUnreachable):
        client.get_forwarded_port()


def test_get_forwarded_port_unauthorized(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key="bad")
    with pytest.raises(GluetunAuthFailed):
        client.get_forwarded_port()


def test_get_forwarded_port_server_error(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunServerError):
        client.get_forwarded_port()
