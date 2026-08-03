"""Unit tests for glueforward.qbittorrent."""

# The authentication state under test has no public accessor.
# pylint: disable=protected-access
# pyright: reportAttributeAccessIssue=false

import httpx
import pytest

from glueforward.main.qbittorrent import (
    QBittorrentAuthenticationNeeded,
    QBittorrentClient,
    QBittorrentForbiddenError,
    QBittorrentServerError,
    QBittorrentUnreachable,
)

CREDENTIALS = {"username": "user", "password": "pass"}
LOGIN_PATH = "/api/v2/auth/login"
SET_PREFS_PATH = "/api/v2/app/setPreferences"


def _login_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"set-cookie": "SID=abc"})


def test_set_port_authenticates_then_succeeds(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(200)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)

    # First call: not authenticated yet, so it authenticates first.
    client.set_port(11111)
    assert client._QBittorrentClient__get_is_authenticated() is True

    # Second call: already authenticated, skips re-authentication.
    client.set_port(22222)


def test_authenticate_forbidden(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentForbiddenError):
        client.set_port(11111)


def test_authenticate_server_error(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentServerError):
        client.set_port(11111)


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadTimeout],
    ids=["connect_error", "read_timeout"],
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
        return httpx.Response(401)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(QBittorrentAuthenticationNeeded):
        client.set_port(11111)
    # The expired session must have been reset.
    assert client._QBittorrentClient__get_is_authenticated() is False


def test_set_port_other_http_error_reraised(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return _login_ok(request)
        return httpx.Response(500)

    mock_httpx(handler)
    client = QBittorrentClient(url="http://qbittorrent", credentials=CREDENTIALS)
    with pytest.raises(httpx.HTTPStatusError):
        client.set_port(11111)


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError, httpx.ReadTimeout],
    ids=["connect_error", "read_timeout"],
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
