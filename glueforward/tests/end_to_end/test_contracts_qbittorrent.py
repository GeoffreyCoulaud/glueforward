"""Contract tests for qBittorrent's WebUI API.

Every branch in QBittorrentClient keys off a status code qBittorrent is
assumed to return. Unit tests can only restate those assumptions; these check
them against qBittorrent itself, one fact per test, so that a release changing
its behaviour fails the test naming the fact rather than surfacing somewhere
in the middle of an end-to-end run.

Nothing here goes through glueforward, and no VPN tunnel is needed, so these
run without any secret.
"""

import time

import httpx

from ..external_contracts import (
    QBITTORRENT_BANNED_STATUS,
    QBITTORRENT_EXPIRED_SESSION_STATUS,
    QBITTORRENT_INVALID_CREDENTIALS_STATUS,
    QBITTORRENT_LOGIN_PATH,
    QBITTORRENT_SET_PREFERENCES_PATH,
)
from .conftest import QBITTORRENT_USERNAME

WRONG_PASSWORD = "definitely-not-the-password"

# Low enough for a test to reach the ban, and to outlive the session.
FAILED_LOGINS_BEFORE_BAN = 3
BAN_DURATION = 10
SESSION_TIMEOUT = 1


def _login(client: httpx.Client, password: str) -> httpx.Response:
    return client.post(
        QBITTORRENT_LOGIN_PATH,
        data={"username": QBITTORRENT_USERNAME, "password": password},
    )


def test_a_valid_login_answers_with_a_session_cookie(qbittorrent, qbittorrent_stranger):
    """Both halves of what QBittorrentClient takes for being authenticated."""
    response = _login(qbittorrent_stranger, qbittorrent.password)

    assert response.is_success
    assert response.cookies, "no cookie to authenticate the next request with"


def test_an_invalid_password_is_rejected(qbittorrent_stranger):
    """The status glueforward stops on, since no retry can fix a wrong password."""
    response = _login(qbittorrent_stranger, WRONG_PASSWORD)

    assert response.status_code == QBITTORRENT_INVALID_CREDENTIALS_STATUS


def test_repeated_failed_logins_are_banned(qbittorrent, qbittorrent_stranger):
    """Why a wrong password is fatal rather than retried, in qBittorrent's terms.

    The last login uses the right password, so what is answered here is the
    ban itself rather than one more rejected attempt.
    """
    qbittorrent.set_preferences(
        web_ui_max_auth_fail_count=FAILED_LOGINS_BEFORE_BAN,
        web_ui_ban_duration=BAN_DURATION,
    )
    for _ in range(FAILED_LOGINS_BEFORE_BAN):
        _login(qbittorrent_stranger, WRONG_PASSWORD)

    response = _login(qbittorrent_stranger, qbittorrent.password)

    assert response.status_code == QBITTORRENT_BANNED_STATUS


def test_an_expired_session_is_rejected(qbittorrent, qbittorrent_stranger):
    """The status glueforward reauthenticates on, rather than shutting down.

    A session expires long before a deployment is restarted: the default
    timeout is an hour, so this is a matter of course.
    """
    qbittorrent.set_preferences(web_ui_session_timeout=SESSION_TIMEOUT)
    login = _login(qbittorrent_stranger, qbittorrent.password)
    qbittorrent_stranger.cookies.update(login.cookies)
    time.sleep(SESSION_TIMEOUT + 1)

    response = qbittorrent_stranger.post(
        QBITTORRENT_SET_PREFERENCES_PATH, data={"json": "{}"}
    )

    assert response.status_code == QBITTORRENT_EXPIRED_SESSION_STATUS
