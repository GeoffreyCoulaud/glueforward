"""Unit tests for glueforward.main."""

# Asserts on Application's internals, which have no public accessor.
# pylint: disable=protected-access

import signal
from unittest.mock import MagicMock

import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import GluetunClient
from glueforward.main.main import Application, ReturnCodes, handle_sigterm, main
from glueforward.main.qbittorrent import QBittorrentClient

# Full, valid environment for building an Application.
VALID_ENV = {
    "GLUETUN_URL": "http://gluetun",
    "GLUETUN_API_KEY": "key",
    "SERVICE_TYPE": "qbittorrent",
    "QBITTORRENT_URL": "http://qbittorrent",
    "QBITTORRENT_USERNAME": "user",
    "QBITTORRENT_PASSWORD": "pass",
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


def test_loop_sets_port_from_gluetun(monkeypatch):
    _set_valid_env(monkeypatch)
    app = Application()
    gluetun = MagicMock()
    service = MagicMock()
    gluetun.get_forwarded_port.return_value = 4242
    app._gluetun = gluetun
    app._service_client = service

    app._loop()

    service.set_port.assert_called_once_with(4242)


def test_run_handles_lifecycle_branches(monkeypatch):
    _set_valid_env(monkeypatch)
    app = Application()
    app._retry_interval = 0
    app._success_interval = 0
    monkeypatch.setattr(
        Application,
        "_loop",
        MagicMock(
            side_effect=[
                RetryableError(message="immediate", retry_immediately=True),
                RetryableError(message="delayed"),
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
    # No sleep on immediate retry; sleep on delayed retry and on success.
    assert sleep.call_count == 2


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
