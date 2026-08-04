"""Unit tests for glueforward.main.application."""

from unittest.mock import MagicMock

import pytest

from glueforward.main.application import Application
from glueforward.main.errors import RetryableError
from glueforward.main.gluetun import GluetunAuthFailed, GluetunServerError
from glueforward.main.port_synchronizer import ForwardedPortNeverCame, NoForwardedPortYet
from glueforward.main.qbittorrent import (
    QBittorrentAuthenticationNeeded,
    QBittorrentInvalidCredentials,
    QBittorrentUnreachable,
)

# Distinct values, so the two intervals cannot be swapped unnoticed.
RETRY_INTERVAL = 7
SUCCESS_INTERVAL = 11


class EndOfTest(Exception):
    """Stands in for an unretryable error, and ends run()'s infinite loop."""


def _make_application(clock, outcomes: list) -> tuple[Application, MagicMock]:
    """An application whose every run has been decided in advance."""
    synchronizer = MagicMock()
    synchronizer.synchronize.side_effect = outcomes
    application = Application(
        synchronizer=synchronizer,
        clock=clock,
        retry_interval=RETRY_INTERVAL,
        success_interval=SUCCESS_INTERVAL,
    )
    return application, synchronizer


def test_a_successful_run_waits_out_the_success_interval(clock):
    application, _ = _make_application(clock, [None, EndOfTest()])

    with pytest.raises(EndOfTest):
        application.run()

    assert clock.slept == [SUCCESS_INTERVAL]


def test_a_retryable_error_waits_out_the_retry_interval(clock):
    """Waiting is what keeps a service that is down from being hammered."""
    application, _ = _make_application(clock, [RetryableError("down"), EndOfTest()])

    with pytest.raises(EndOfTest):
        application.run()

    assert clock.slept == [RETRY_INTERVAL]


def test_an_immediate_retry_does_not_wait(clock):
    """Reauthenticating costs one request, so waiting on it is dead time."""
    outcomes = [RetryableError("expired", retry_immediately=True), EndOfTest()]
    application, _ = _make_application(clock, outcomes)

    with pytest.raises(EndOfTest):
        application.run()

    assert clock.slept == []


def test_an_unretryable_error_is_left_to_the_caller(clock):
    """Turning it into an exit code is the entry point's job, not the loop's."""
    application, synchronizer = _make_application(clock, [ValueError("unretryable")])

    with pytest.raises(ValueError):
        application.run()

    assert synchronizer.synchronize.call_count == 1


@pytest.mark.parametrize(
    "error",
    [
        GluetunServerError,
        NoForwardedPortYet,
        QBittorrentUnreachable,
        QBittorrentAuthenticationNeeded,
    ],
    ids=["gluetun_outage", "no_forwarded_port", "qbittorrent_down", "session_expired"],
)
def test_run_survives_a_service_being_away(clock, error):
    """Each of these is routine: tunnels renegotiate, sessions expire, stacks restart."""
    application, synchronizer = _make_application(
        clock, [error(), error(), None, EndOfTest()]
    )

    with pytest.raises(EndOfTest):
        application.run()

    # Two failures, a recovery, and only then the exception ending the test.
    assert synchronizer.synchronize.call_count == 4


@pytest.mark.parametrize(
    "error",
    [GluetunAuthFailed, QBittorrentInvalidCredentials, ForwardedPortNeverCame],
    ids=["bad_api_key", "bad_credentials", "port_forwarding_off"],
)
def test_run_stops_on_a_misconfiguration_without_retrying(clock, error):
    """Retrying cannot fix a wrong secret, and gets us banned by qBittorrent."""
    application, synchronizer = _make_application(clock, [error()])

    with pytest.raises(error):
        application.run()

    assert synchronizer.synchronize.call_count == 1
