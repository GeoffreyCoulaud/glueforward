"""Unit tests for glueforward.main.main, the entry point.

What is left here is what only the entry point does: reading the environment,
configuring logging process-wide, wiring the pieces together, and turning
whatever stops the application into an exit code.
"""

import logging
import signal
from unittest.mock import MagicMock

import httpx
import pytest

from glueforward.main.application import Application
from glueforward.main.config import Config, QBittorrentConfig
from glueforward.main.errors import ReturnCodes
from glueforward.main.main import (
    build_port_synchronizer,
    configure_logging,
    handle_sigterm,
    main,
)

from ..external_contracts import (
    GLUETUN_PORT_FORWARD_PATH,
    GLUETUN_PORT_KEY,
    QBITTORRENT_LOGIN_PATH,
    QBITTORRENT_SET_PREFERENCES_PATH,
)
from .conftest import GLUETUN_API_KEY, QBITTORRENT_PASSWORD

FORWARDED_PORT = 51413

CONFIG = Config(
    gluetun_url="http://gluetun",
    gluetun_api_key=GLUETUN_API_KEY,
    gluetun_port_wait_duration=300,
    retry_interval=10,
    success_interval=300,
    service=QBittorrentConfig(
        url="http://qbittorrent",
        username="user",
        password=QBITTORRENT_PASSWORD,
    ),
)


@pytest.fixture(autouse=True)
def restore_sigterm_handler():
    """main() installs a process-wide handler, which must not outlive the test."""
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


@pytest.fixture(autouse=True)
def restore_logging():
    """configure_logging reconfigures logging process-wide, tests included."""
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    levels = (root.level, httpx_logger.level)
    handlers = root.handlers[:]
    yield
    root.setLevel(levels[0])
    httpx_logger.setLevel(levels[1])
    root.handlers[:] = handlers


def _serve_a_forwarded_port(request: httpx.Request) -> httpx.Response:
    """Answer both services, so a whole cycle goes through."""
    if request.url.path == GLUETUN_PORT_FORWARD_PATH:
        return httpx.Response(200, json={GLUETUN_PORT_KEY: FORWARDED_PORT})
    return httpx.Response(200, headers={"set-cookie": "SID=abc"})


@pytest.mark.parametrize(
    "environment_log_level, expected",
    [("DEBUG", "DEBUG"), ("NOPE", "INFO"), (None, "INFO")],
    ids=["valid", "invalid", "unset"],
)
def test_the_log_level_comes_from_the_environment(
    monkeypatch, environment_log_level, expected
):
    """An unreadable LOG_LEVEL must not be a reason to refuse to start."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    if environment_log_level is not None:
        monkeypatch.setenv("LOG_LEVEL", environment_log_level)

    configure_logging()

    levels = logging.getLevelNamesMapping()
    assert logging.getLogger().getEffectiveLevel() == levels[expected]


@pytest.mark.parametrize(
    "log_level, httpx_level",
    [("INFO", "WARNING"), ("DEBUG", "DEBUG")],
)
def test_httpx_is_silenced_unless_debugging(monkeypatch, log_level, httpx_level):
    """httpx logs a line per request, drowning out everything worth reading."""
    monkeypatch.setenv("LOG_LEVEL", log_level)

    configure_logging()

    levels = logging.getLevelNamesMapping()
    assert logging.getLogger("httpx").getEffectiveLevel() == levels[httpx_level]


def test_the_synchronizer_is_wired_to_the_configured_services(mock_httpx, clock):
    """One whole cycle in memory, which is what proves the wiring holds."""
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        return _serve_a_forwarded_port(request)

    mock_httpx(handler)

    build_port_synchronizer(CONFIG, clock).synchronize()

    assert requested == [
        ("GET", GLUETUN_PORT_FORWARD_PATH),
        ("POST", QBITTORRENT_LOGIN_PATH),
        ("POST", QBITTORRENT_SET_PREFERENCES_PATH),
    ]


def test_a_successful_cycle_logs_no_secret(mock_httpx, clock, caplog):
    """Logs get pasted into issues, so they must not carry credentials."""
    caplog.set_level(logging.DEBUG)
    mock_httpx(_serve_a_forwarded_port)

    build_port_synchronizer(CONFIG, clock).synchronize()

    assert caplog.text, "nothing was captured, so the assertions below prove nothing"
    assert GLUETUN_API_KEY not in caplog.text
    assert QBITTORRENT_PASSWORD not in caplog.text


@pytest.mark.usefixtures("valid_environment")
def test_main_runs_the_application(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(Application, "run", run)

    main()

    run.assert_called_once()


@pytest.mark.usefixtures("valid_environment")
def test_main_installs_the_sigterm_handler(monkeypatch):
    monkeypatch.setattr(Application, "run", MagicMock())

    main()

    assert signal.getsignal(signal.SIGTERM) is handle_sigterm


def test_sigterm_exits_without_an_error_code():
    with pytest.raises(SystemExit) as exit_attempt:
        handle_sigterm(signal.SIGTERM, None)

    assert exit_attempt.value.code == 0


@pytest.mark.usefixtures("valid_environment")
def test_main_exits_on_a_configuration_error(monkeypatch, capsys):
    """The exit code is what a `docker compose` log leaves an operator with."""
    monkeypatch.delenv("GLUETUN_URL")

    with pytest.raises(SystemExit) as exit_attempt:
        main()

    assert exit_attempt.value.code == ReturnCodes.MISSING_ENVIRONMENT_VARIABLE
    # configure_logging drops the handlers caplog installs, so read stderr.
    assert "GLUETUN_URL" in capsys.readouterr().err


@pytest.mark.usefixtures("valid_environment")
def test_main_exits_on_an_unretryable_error(monkeypatch):
    monkeypatch.setattr(Application, "run", MagicMock(side_effect=ValueError("boom")))

    with pytest.raises(SystemExit) as exit_attempt:
        main()

    assert exit_attempt.value.code == ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
