"""Unit tests for glueforward.main.gluetun.

The status codes these tests script are the ones gluetun really returns,
pinned against a live control server by the end-to-end contract tests.
"""

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import (
    GluetunAuthFailed,
    GluetunClient,
    GluetunServerError,
    GluetunUnexpectedResponse,
    GluetunUnreachable,
)

from ..external_contracts import (
    GLUETUN_API_KEY_HEADER,
    GLUETUN_INVALID_API_KEY_STATUS,
    GLUETUN_NO_FORWARDED_PORT,
    GLUETUN_PORT_FORWARD_PATH,
    GLUETUN_PORT_KEY,
)

FORWARDED_PORT = 51413


def _make_client(api_key: None | str = None) -> GluetunClient:
    return GluetunClient(url="http://gluetun", api_key=api_key)


def _answer(port: int) -> httpx.Response:
    return httpx.Response(200, json={GLUETUN_PORT_KEY: port})


@pytest.mark.parametrize(
    "error, is_retryable",
    [
        (GluetunUnreachable, True),
        (GluetunServerError, True),
        (GluetunAuthFailed, False),
        (GluetunUnexpectedResponse, False),
    ],
)
def test_retry_policy(error, is_retryable):
    """An unreachable gluetun comes back on its own; a rejected API key never does."""
    assert issubclass(error, RetryableError) is is_retryable


def test_init_sets_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers[GLUETUN_API_KEY_HEADER] == "secret"
        return _answer(FORWARDED_PORT)

    mock_httpx(handler)
    assert _make_client(api_key="secret").get_forwarded_port() == FORWARDED_PORT


def test_init_without_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert GLUETUN_API_KEY_HEADER not in request.headers
        return _answer(FORWARDED_PORT)

    mock_httpx(handler)
    assert _make_client().get_forwarded_port() == FORWARDED_PORT


def test_get_forwarded_port_success(mock_httpx):
    mock_httpx(lambda _: _answer(FORWARDED_PORT))

    assert _make_client().get_forwarded_port() == FORWARDED_PORT


def test_get_forwarded_port_requests_the_control_server_endpoint(mock_httpx):
    """The endpoint is gluetun's, so nothing in this repository can vouch for it."""
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return _answer(FORWARDED_PORT)

    mock_httpx(handler)
    _make_client().get_forwarded_port()

    assert seen == [("GET", GLUETUN_PORT_FORWARD_PATH)]


def test_no_forwarded_port_is_reported_as_none(mock_httpx):
    """Whether that is worth waiting out is the caller's to judge, not ours."""
    mock_httpx(lambda _: _answer(GLUETUN_NO_FORWARDED_PORT))

    assert _make_client().get_forwarded_port() is None


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_error", "read_timeout", "connect_timeout"],
)
def test_get_forwarded_port_unreachable(mock_httpx, exception):
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception("boom")

    mock_httpx(handler)
    with pytest.raises(GluetunUnreachable):
        _make_client().get_forwarded_port()


def test_get_forwarded_port_unauthorized(mock_httpx):
    mock_httpx(
        lambda _: httpx.Response(GLUETUN_INVALID_API_KEY_STATUS, text="unauthorized")
    )

    with pytest.raises(GluetunAuthFailed):
        _make_client(api_key="bad").get_forwarded_port()


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_get_forwarded_port_server_error(mock_httpx, status_code):
    """A 5xx is gluetun having a bad moment, so it is worth waiting out."""
    mock_httpx(lambda _: httpx.Response(status_code, text="server error"))

    with pytest.raises(GluetunServerError):
        _make_client().get_forwarded_port()


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
    mock_httpx(lambda _: response)

    with pytest.raises(GluetunUnexpectedResponse):
        _make_client().get_forwarded_port()
