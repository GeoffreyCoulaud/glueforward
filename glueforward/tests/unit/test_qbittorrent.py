"""Unit tests for glueforward.qbittorrent.

The status codes these tests script are the ones qBittorrent really returns,
pinned against a live instance by the end-to-end tests.
"""

# The authentication state under test has no public accessor.
# pylint: disable=protected-access

import json
from urllib.parse import parse_qs, urlencode

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.qbittorrent import (
    QBittorrentAuthenticationNeeded,
    QBittorrentBanned,
    QBittorrentClient,
    QBittorrentInvalidCredentials,
    QBittorrentServerError,
    QBittorrentUnexpectedResponse,
    QBittorrentUnreachable,
)

CREDENTIALS = {"username": "user", "password": "pass"}
LOGIN_PATH = "/api/v2/auth/login"
SET_PREFS_PATH = "/api/v2/app/setPreferences"


@pytest.mark.parametrize(
    "error, is_retryable",
    [
        (QBittorrentUnreachable, True),
        (QBittorrentServerError, True),
        (QBittorrentAuthenticationNeeded, True),
        (QBittorrentInvalidCredentials, False),
        (QBittorrentUnexpectedResponse, False),
        (QBittorrentBanned, False),
    ],
)
def test_retry_policy(error, is_retryable):
    """Retrying a rejected password only gets the caller banned, and a ban
    lasts web_ui_ban_duration whatever we do, so both are worth stopping for."""
    assert issubclass(error, RetryableError) is is_retryable


def test_only_reauthentication_is_retried_immediately():
    """Waiting is what keeps a service that is down from being hammered."""
    assert QBittorrentAuthenticationNeeded().get_retry_immediately() is True
    assert QBittorrentUnreachable().get_retry_immediately() is False


def _login_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(204, headers={"set-cookie": "SID=abc"})


def test_set_port_authenticates_then_succeeds(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(200)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)

    # First call: not authenticated yet, so it authenticates first.
    client.set_port(11111)
    assert client._get_is_authenticated() is True

    # Second call: already authenticated, skips re-authentication.
    client.set_port(22222)


def test_set_port_sends_the_requests_qbittorrent_expects(mock_httpx):
    """Both endpoints take form data, and setPreferences wraps its own JSON."""
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content.decode()))
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(200)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)

    client.set_port(4242)

    assert len(seen) == 2
    assert seen[0] == ("POST", LOGIN_PATH, urlencode(CREDENTIALS))
    assert seen[1][:2] == ("POST", SET_PREFS_PATH)
    # A forwarded port is useless if qBittorrent may still pick its own.
    assert json.loads(parse_qs(seen[1][2])["json"][0]) == {
        "listen_port": 4242,
        "random_port": False,
        "upnp": False,
    }


def test_authenticate_invalid_credentials(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentInvalidCredentials):
        client.set_port(11111)


def test_authenticate_banned(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Your IP address has been banned")

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentBanned):
        client.set_port(11111)


def test_authenticate_server_error(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentServerError):
        client.set_port(11111)


@pytest.mark.parametrize(
    "status_code", [404, 400, 302], ids=["not_found", "bad_request", "redirect"]
)
def test_authenticate_unexpected_response(mock_httpx, status_code):
    """A wrong QBITTORRENT_URL answers like this, and no retry will fix it."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="nothing to do with qBittorrent")

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentUnexpectedResponse):
        client.set_port(11111)


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_error", "read_timeout", "connect_timeout"],
)
def test_authenticate_unreachable(mock_httpx, exception):
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception("boom")

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentUnreachable):
        client.set_port(11111)


def test_set_port_session_expired(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(403)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentAuthenticationNeeded):
        client.set_port(11111)
    # The expired session must have been reset.
    assert client._get_is_authenticated() is False


def test_set_port_server_error(mock_httpx):
    """Authenticating already waits out a 5xx, and so should writing the port."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(500)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentServerError):
        client.set_port(11111)


def test_set_port_unexpected_response(mock_httpx):
    """Authentication went through, so a 404 here is the wrong URL entirely."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(404)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentUnexpectedResponse):
        client.set_port(11111)


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout],
    ids=["connect_error", "read_error", "read_timeout", "connect_timeout"],
)
def test_set_port_unreachable(mock_httpx, exception):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        raise exception("boom")

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentUnreachable):
        client.set_port(11111)
