"""Unit tests for glueforward.gluetun."""

import logging

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import (
    MISSING_PORT_ERROR_INTERVAL,
    GluetunAuthFailed,
    GluetunClient,
    GluetunNoForwardedPort,
    GluetunServerError,
    GluetunUnexpectedResponse,
    GluetunUnreachable,
)


@pytest.mark.parametrize(
    "error, is_retryable",
    [
        (GluetunUnreachable, True),
        (GluetunServerError, True),
        (GluetunNoForwardedPort, True),
        (GluetunAuthFailed, False),
        (GluetunUnexpectedResponse, False),
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


def test_a_port_that_never_comes_is_eventually_warned_about(
    mock_httpx, monkeypatch, caplog
):
    """VPN_PORT_FORWARDING left off is otherwise silent: gluetun reports the
    same 0 as a tunnel that is still negotiating one."""
    port = 0

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": port})

    clock = 0.0
    monkeypatch.setattr("glueforward.main.gluetun.monotonic", lambda: clock)
    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            with pytest.raises(GluetunNoForwardedPort):
                client.get_forwarded_port()
        assert not caplog.records, "warned before a tunnel could have negotiated"

        clock = MISSING_PORT_ERROR_INTERVAL + 1
        with pytest.raises(GluetunNoForwardedPort):
            client.get_forwarded_port()
        assert len(caplog.records) == 1
        assert "VPN_PORT_FORWARDING" in caplog.text

        # Repeats rather than warning once, since the fix is out of our hands.
        clock += MISSING_PORT_ERROR_INTERVAL + 1
        with pytest.raises(GluetunNoForwardedPort):
            client.get_forwarded_port()
        assert len(caplog.records) == 2


def test_a_forwarded_port_clears_the_warning(mock_httpx, monkeypatch, caplog):
    """A tunnel that took its time is not worth warning about afterwards."""
    port = 0

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": port})

    clock = 0.0
    monkeypatch.setattr("glueforward.main.gluetun.monotonic", lambda: clock)
    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(GluetunNoForwardedPort):
            client.get_forwarded_port()
        port = 51413
        assert client.get_forwarded_port() == 51413

        port = 0
        clock = MISSING_PORT_ERROR_INTERVAL + 1
        with pytest.raises(GluetunNoForwardedPort):
            client.get_forwarded_port()

        assert not caplog.records


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_error", "read_timeout", "connect_timeout"],
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


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_get_forwarded_port_server_error(mock_httpx, status_code):
    """A 5xx is gluetun having a bad moment, so it is worth waiting out."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="server error")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunServerError):
        client.get_forwarded_port()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, text="Not Found"),
        httpx.Response(403, text="Forbidden"),
        httpx.Response(302, headers={"location": "/login"}),
        httpx.Response(200, text="<html>a login page</html>"),
        httpx.Response(200, json={"ports": [51413]}),
        httpx.Response(200, json=[51413]),
    ],
    ids=["not_found", "forbidden", "redirect", "html", "no_port_key", "not_an_object"],
)
def test_get_forwarded_port_unexpected_response(mock_httpx, response):
    """A wrong GLUETUN_URL answers like this, and no retry will fix it."""

    def handler(_: httpx.Request) -> httpx.Response:
        return response

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunUnexpectedResponse):
        client.get_forwarded_port()
