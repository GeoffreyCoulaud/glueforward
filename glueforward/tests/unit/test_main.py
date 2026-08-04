"""Unit tests for glueforward.main."""

# Asserts on Application's internals, which have no public accessor.
# pylint: disable=protected-access

import io
import logging
import signal
from unittest.mock import MagicMock, call

import httpx
import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import (
    GluetunAuthFailed,
    GluetunClient,
    GluetunNoForwardedPort,
    GluetunServerError,
)
from glueforward.main.main import Application, ReturnCodes, handle_sigterm, main
from glueforward.main.qbittorrent import (
    QBittorrentAuthenticationNeeded,
    QBittorrentClient,
    QBittorrentInvalidCredentials,
    QBittorrentUnreachable,
)

# Distinctive enough to be searched for in the logs.
GLUETUN_API_KEY = "gluetun-api-key-3f9a2c"
QBITTORRENT_PASSWORD = "qbittorrent-password-7d1e04"

# Full, valid environment for building an Application.
VALID_ENV = {
    "GLUETUN_URL": "http://gluetun",
    "GLUETUN_API_KEY": GLUETUN_API_KEY,
    "SERVICE_TYPE": "qbittorrent",
    "QBITTORRENT_URL": "http://qbittorrent",
    "QBITTORRENT_USERNAME": "user",
    "QBITTORRENT_PASSWORD": QBITTORRENT_PASSWORD,
}


def _set_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(autouse=True)
def restore_sigterm_handler():
    """main() installs a process-wide handler, which must not outlive the test."""
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


def test_init_with_valid_log_level(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    app = Application()

    assert isinstance(app._gluetun, GluetunClient)
    assert isinstance(app._service_client, QBittorrentClient)
    assert app._retry_interval == 10
    assert app._success_interval == 300


def test_init_with_invalid_log_level_defaults_to_info(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "NOPE")

    app = Application()  # must not raise; LOG_LEVEL falls back to INFO

    assert isinstance(app._service_client, QBittorrentClient)


@pytest.mark.parametrize(
    "name", ["RETRY_INTERVAL", "SUCCESS_INTERVAL", "GLUETUN_PORT_WAIT_DURATION"]
)
@pytest.mark.parametrize(
    "value",
    ["5m", "10s", "", "2.5", "five"],
    ids=["minutes", "seconds", "empty", "decimal", "word"],
)
def test_init_non_numeric_interval_exits(monkeypatch, capsys, name, value):
    """Borrowing another tool's duration syntax is the obvious mistake to make."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit) as exc:
        Application()

    assert exc.value.code == ReturnCodes.INVALID_ENVIRONMENT_VARIABLE
    # _configure_logging drops the handlers caplog installs, so read stderr.
    logs = capsys.readouterr().err
    assert name in logs
    assert repr(value) in logs


def test_init_intervals_are_read_from_the_environment(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("RETRY_INTERVAL", "42")
    monkeypatch.setenv("SUCCESS_INTERVAL", "4242")

    app = Application()

    assert app._retry_interval == 42
    assert app._success_interval == 4242


@pytest.mark.parametrize(
    "environment, expected",
    [({}, 1000 + 300), ({"GLUETUN_PORT_WAIT_DURATION": "42"}, 1000 + 42)],
    ids=["default", "from_the_environment"],
)
def test_init_gives_gluetun_a_deadline_for_its_first_port(
    monkeypatch, environment, expected
):
    """The deadline is counted from startup, so it has to be stamped here."""
    _set_valid_env(monkeypatch)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("glueforward.main.main.monotonic", lambda: 1000.0)

    app = Application()

    assert app._gluetun._wait_for_port_until == expected


def test_init_missing_required_env_exits(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.delenv("GLUETUN_URL")

    with pytest.raises(SystemExit) as exc:
        Application()
    assert exc.value.code == ReturnCodes.MISSING_ENVIRONMENT_VARIABLE


def test_init_unknown_service_type_exits(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("SERVICE_TYPE", "transmission")

    with pytest.raises(SystemExit) as exc:
        Application()
    assert exc.value.code == ReturnCodes.UNKNOWN_SERVICE_TYPE


def test_every_tick_writes_the_port_again(monkeypatch):
    """Nothing is remembered between ticks: anything may have edited it since."""
    _set_valid_env(monkeypatch)
    app = Application()
    gluetun = MagicMock()
    service = MagicMock()
    gluetun.get_forwarded_port.return_value = 4242
    app._gluetun = gluetun
    app._service_client = service

    app._loop()
    app._loop()

    assert service.set_port.call_args_list == [call(4242), call(4242)]


def test_run_handles_lifecycle_branches(monkeypatch):
    _set_valid_env(monkeypatch)
    app = Application()
    # Distinct values, so the two intervals cannot be swapped unnoticed.
    app._retry_interval = 7
    app._success_interval = 11
    monkeypatch.setattr(
        Application,
        "_loop",
        MagicMock(
            side_effect=[
                RetryableError("immediate", retry_immediately=True),
                RetryableError("delayed"),
                None,  # success path
                ValueError("unretryable"),  # unretryable -> shutdown
            ]
        ),
    )
    sleep = MagicMock()
    monkeypatch.setattr("glueforward.main.main.sleep", sleep)

    with pytest.raises(SystemExit) as exc:
        app.run()

    assert exc.value.code == ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    # No sleep on immediate retry, then each outcome waits out its own interval.
    assert sleep.call_args_list == [call(7), call(11)]


def _patch_loop(monkeypatch, side_effect: list) -> MagicMock:
    """Drive run() through the given outcomes, and return the patched loop."""
    loop = MagicMock(side_effect=side_effect)
    monkeypatch.setattr(Application, "_loop", loop)
    monkeypatch.setattr("glueforward.main.main.sleep", MagicMock())
    return loop


@pytest.mark.parametrize(
    "error",
    [
        GluetunServerError,
        GluetunNoForwardedPort,
        QBittorrentUnreachable,
        QBittorrentAuthenticationNeeded,
    ],
    ids=["gluetun_outage", "no_forwarded_port", "qbittorrent_down", "session_expired"],
)
def test_run_survives_a_service_being_away(monkeypatch, error):
    """Each of these is routine: tunnels renegotiate, sessions expire, stacks restart."""
    _set_valid_env(monkeypatch)
    app = Application()
    loop = _patch_loop(
        monkeypatch, [error(), error(), None, ValueError("end of the test")]
    )

    with pytest.raises(SystemExit):
        app.run()

    # Two failures, a recovery, and only then the exception ending the test.
    assert loop.call_count == 4


@pytest.mark.parametrize(
    "error",
    [GluetunAuthFailed, QBittorrentInvalidCredentials],
    ids=["bad_api_key", "bad_credentials"],
)
def test_run_shuts_down_on_a_misconfiguration_without_retrying(monkeypatch, error):
    """Retrying cannot fix a wrong secret, and gets us banned by qBittorrent."""
    _set_valid_env(monkeypatch)
    app = Application()
    loop = _patch_loop(monkeypatch, [error()])

    with pytest.raises(SystemExit) as exc:
        app.run()

    assert exc.value.code == ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    assert loop.call_count == 1


@pytest.mark.parametrize(
    "log_level, httpx_level",
    [("INFO", "WARNING"), ("DEBUG", "DEBUG")],
)
def test_httpx_is_silenced_unless_debugging(monkeypatch, log_level, httpx_level):
    """httpx logs a line per request, drowning out everything worth reading."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", log_level)

    Application()

    levels = logging.getLevelNamesMapping()
    assert logging.getLogger("httpx").getEffectiveLevel() == levels[httpx_level]
    assert logging.getLogger().getEffectiveLevel() == levels[log_level]


def test_a_successful_cycle_logs_no_secret(monkeypatch, mock_httpx):
    """Logs get pasted into issues, so they must not carry credentials."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/portforward":
            return httpx.Response(200, json={"port": 4242})
        return httpx.Response(200, headers={"set-cookie": "SID=abc"})

    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    mock_httpx(handler)
    app = Application()
    # dictConfig drops the root handlers caplog installs, so capture our own.
    logs = io.StringIO()
    capture = logging.StreamHandler(logs)
    logging.getLogger().addHandler(capture)
    try:
        app._loop()
    finally:
        logging.getLogger().removeHandler(capture)

    assert GLUETUN_API_KEY not in logs.getvalue()
    assert QBITTORRENT_PASSWORD not in logs.getvalue()


def test_main_runs_application(monkeypatch):
    _set_valid_env(monkeypatch)
    run = MagicMock()
    monkeypatch.setattr(Application, "run", run)

    main()

    run.assert_called_once()


def test_main_installs_the_sigterm_handler(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setattr(Application, "run", MagicMock())

    main()

    assert signal.getsignal(signal.SIGTERM) is handle_sigterm


def test_sigterm_exits_without_an_error_code():
    with pytest.raises(SystemExit) as exc:
        handle_sigterm(signal.SIGTERM, None)
    assert exc.value.code == 0
