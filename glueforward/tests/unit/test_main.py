"""Unit tests for glueforward.main."""

# _setup() exposes no accessors, so its wiring is only observable through the
# name-mangled attributes it sets.
# pylint: disable=protected-access
# pyright: reportAttributeAccessIssue=false

from unittest.mock import MagicMock

import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import GluetunClient
from glueforward.main.main import Application, ReturnCodes, main
from glueforward.main.qbittorrent import QBittorrentClient

# Full, valid environment for _setup.
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


def test_setup_with_valid_log_level(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    app = Application()
    app._setup()

    assert isinstance(app._Application__gluetun, GluetunClient)
    assert isinstance(app._Application__service_client, QBittorrentClient)
    assert app._Application__retry_interval == 10
    assert app._Application__success_interval == 300


def test_setup_with_invalid_log_level_defaults_to_info(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "NOPE")

    app = Application()
    app._setup()  # must not raise; LOG_LEVEL falls back to INFO

    assert isinstance(app._Application__service_client, QBittorrentClient)


def test_setup_missing_required_env_exits(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.delenv("GLUETUN_URL")

    app = Application()
    with pytest.raises(SystemExit) as exc:
        app._setup()
    assert exc.value.code == ReturnCodes.MISSING_ENVIRONMENT_VARIABLE


def test_setup_unknown_service_type_exits(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("SERVICE_TYPE", "transmission")

    app = Application()
    with pytest.raises(SystemExit) as exc:
        app._setup()
    assert exc.value.code == ReturnCodes.UNKNOWN_SERVICE_TYPE


def test_loop_sets_port_from_gluetun():
    app = Application()
    gluetun = MagicMock()
    service = MagicMock()
    gluetun.get_forwarded_port.return_value = 4242
    app._Application__gluetun = gluetun
    app._Application__service_client = service

    app._Application__loop()

    service.set_port.assert_called_once_with(4242)


def test_run_handles_lifecycle_branches(monkeypatch):
    app = Application()
    app._Application__retry_interval = 0
    app._Application__success_interval = 0
    monkeypatch.setattr(Application, "_setup", lambda self: None)
    monkeypatch.setattr(
        Application,
        "_Application__loop",
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
    run = MagicMock()
    monkeypatch.setattr(Application, "run", run)

    main()

    run.assert_called_once()
