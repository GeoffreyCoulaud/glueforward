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
from glueforward.main.errors import ReturnCodes
from glueforward.main.main import configure_logging, handle_sigterm, main

from ..external_contracts import (
    GLUETUN_PORT_FORWARD_PATH,
    GLUETUN_PORT_KEY,
    QBITTORRENT_LOGIN_PATH,
    QBITTORRENT_SET_PREFERENCES_PATH,
)
from .conftest import GLUETUN_API_KEY, QBITTORRENT_PASSWORD, EndOfTest

FORWARDED_PORT = 51413


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


def _serve_one_cycle(requested: list[tuple[str, str]]):
    """Answer both services once, then cut short the endless loop.

    Asking gluetun a second time means the first cycle went all the way
    through, which is the only outcome these tests are after.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        is_gluetun = request.url.path == GLUETUN_PORT_FORWARD_PATH
        if requested and is_gluetun:
            raise EndOfTest()
        requested.append((request.method, request.url.path))
        if is_gluetun:
            return httpx.Response(200, json={GLUETUN_PORT_KEY: FORWARDED_PORT})
        return httpx.Response(200, headers={"set-cookie": "SID=abc"})

    return handler


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


@pytest.mark.usefixtures("valid_environment")
def test_main_wires_the_application_to_the_configured_services(monkeypatch, mock_httpx):
    """One whole cycle in memory, which is what proves the wiring holds."""
    monkeypatch.setenv("SUCCESS_INTERVAL", "0")
    requested: list[tuple[str, str]] = []
    mock_httpx(_serve_one_cycle(requested))

    with pytest.raises(SystemExit):
        main()

    assert requested == [
        ("GET", GLUETUN_PORT_FORWARD_PATH),
        ("POST", QBITTORRENT_LOGIN_PATH),
        ("POST", QBITTORRENT_SET_PREFERENCES_PATH),
    ]


@pytest.mark.usefixtures("valid_environment")
def test_a_successful_cycle_logs_no_secret(monkeypatch, mock_httpx, capsys):
    """Logs get pasted into issues, so they must not carry credentials."""
    monkeypatch.setenv("SUCCESS_INTERVAL", "0")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    mock_httpx(_serve_one_cycle([]))

    with pytest.raises(SystemExit):
        main()

    # configure_logging drops the handlers caplog installs, so read stderr.
    logs = capsys.readouterr().err
    assert logs, "nothing was captured, so the assertions below prove nothing"
    assert GLUETUN_API_KEY not in logs
    assert QBITTORRENT_PASSWORD not in logs


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
