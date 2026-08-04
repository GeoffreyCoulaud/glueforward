"""Unit tests for glueforward.gluetun."""

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import (
    GluetunAuthFailed,
    GluetunClient,
    GluetunFailedToForwardPort,
    GluetunNoForwardedPort,
    GluetunServerError,
    GluetunUnexpectedResponse,
    GluetunUnreachable,
)

DEADLINE = 300.0


def _make_client(
    api_key: None | str = None,
    wait_for_port_until: float = 0.0,
) -> GluetunClient:
    """A client whose deadline for a first port has passed, unless stated."""
    return GluetunClient(
        url="http://gluetun", api_key=api_key, wait_for_port_until=wait_for_port_until
    )


@pytest.mark.parametrize(
    "error, is_retryable",
    [
        (GluetunUnreachable, True),
        (GluetunServerError, True),
        (GluetunNoForwardedPort, True),
        (GluetunAuthFailed, False),
        (GluetunUnexpectedResponse, False),
        (GluetunFailedToForwardPort, False),
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
    client = _make_client(api_key="secret")
    assert client.get_forwarded_port() == 1


def test_init_without_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-API-Key" not in request.headers
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    client = _make_client()
    assert client.get_forwarded_port() == 1


def test_get_forwarded_port_success(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": 50000})

    mock_httpx(handler)
    client = _make_client()
    assert client.get_forwarded_port() == 50000


def test_get_forwarded_port_requests_the_control_server_endpoint(mock_httpx):
    """The endpoint is gluetun's, so nothing in this repository can vouch for it."""
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    _make_client().get_forwarded_port()

    assert seen == [("GET", "/v1/portforward")]


@pytest.fixture(name="clock")
def clock_fixture(monkeypatch):
    """A monotonic clock the test moves by hand, starting at 0."""

    class Clock:
        now = 0.0

    monkeypatch.setattr("glueforward.main.gluetun.monotonic", lambda: Clock.now)
    return Clock


@pytest.fixture(name="forwarded_port")
def forwarded_port_fixture(mock_httpx):
    """What gluetun answers, which a test changes between two calls."""

    class Gluetun:
        port = 0

    mock_httpx(lambda _: httpx.Response(200, json={"port": Gluetun.port}))
    return Gluetun


def test_a_missing_first_port_is_waited_for(clock, forwarded_port):
    """Negotiating a tunnel takes a while, and reports 0 all the way through."""
    forwarded_port.port = 0
    client = _make_client(wait_for_port_until=DEADLINE)

    for clock.now in (0.0, DEADLINE / 2, DEADLINE - 1):
        with pytest.raises(GluetunNoForwardedPort):
            client.get_forwarded_port()


def test_a_first_port_that_never_comes_is_given_up_on(clock, forwarded_port):
    """Waiting forever hides the one thing that would explain it, the setting."""
    forwarded_port.port = 0
    client = _make_client(wait_for_port_until=DEADLINE)
    with pytest.raises(GluetunNoForwardedPort):
        client.get_forwarded_port()

    clock.now = DEADLINE

    with pytest.raises(GluetunFailedToForwardPort) as error:
        client.get_forwarded_port()
    assert "VPN_PORT_FORWARDING" in str(error.value)


def test_a_port_lost_after_the_deadline_is_only_a_renegotiation(clock, forwarded_port):
    """A tunnel that dropped one port will get another, however late it is."""
    client = _make_client(wait_for_port_until=DEADLINE)
    forwarded_port.port = 51413
    assert client.get_forwarded_port() == 51413

    forwarded_port.port = 0
    clock.now = DEADLINE * 10

    # Fatal here would take the deployment down whenever the tunnel renegotiates.
    with pytest.raises(GluetunNoForwardedPort):
        client.get_forwarded_port()


def test_a_first_port_arriving_late_is_still_accepted(clock, forwarded_port):
    """The deadline only ends the wait, it does not refuse what comes after."""
    client = _make_client(wait_for_port_until=DEADLINE)
    forwarded_port.port = 51413
    clock.now = DEADLINE * 10

    assert client.get_forwarded_port() == 51413


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_error", "read_timeout", "connect_timeout"],
)
def test_get_forwarded_port_unreachable(mock_httpx, exception):
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception("boom")

    mock_httpx(handler)
    client = _make_client()
    with pytest.raises(GluetunUnreachable):
        client.get_forwarded_port()


def test_get_forwarded_port_unauthorized(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    mock_httpx(handler)
    client = _make_client(api_key="bad")
    with pytest.raises(GluetunAuthFailed):
        client.get_forwarded_port()


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_get_forwarded_port_server_error(mock_httpx, status_code):
    """A 5xx is gluetun having a bad moment, so it is worth waiting out."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="server error")

    mock_httpx(handler)
    client = _make_client()
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
    client = _make_client()
    with pytest.raises(GluetunUnexpectedResponse):
        client.get_forwarded_port()
