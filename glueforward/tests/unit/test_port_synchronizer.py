"""Unit tests for glueforward.main.port_synchronizer."""

import logging
from unittest.mock import MagicMock, call

import pytest

from glueforward.main.errors import RetryableError
from glueforward.main.port_synchronizer import (
    ForwardedPortNeverCame,
    NoForwardedPortYet,
    PortSynchronizer,
)

WAIT_FOR_FIRST_PORT = 300.0
FORWARDED_PORT = 51413


@pytest.fixture(name="forwarder")
def forwarder_fixture() -> MagicMock:
    """The VPN side, whose forwarded port a test changes between two runs."""
    forwarder = MagicMock()
    forwarder.get_forwarded_port.return_value = None
    return forwarder


@pytest.fixture(name="service")
def service_fixture() -> MagicMock:
    return MagicMock()


@pytest.fixture(name="synchronizer")
def synchronizer_fixture(forwarder, service, clock) -> PortSynchronizer:
    """A synchronizer whose deadline for a first port is WAIT_FOR_FIRST_PORT away."""
    return PortSynchronizer(
        forwarder=forwarder,
        service=service,
        clock=clock,
        wait_for_first_port_duration=WAIT_FOR_FIRST_PORT,
    )


@pytest.mark.parametrize(
    "error, is_retryable",
    [(NoForwardedPortYet, True), (ForwardedPortNeverCame, False)],
)
def test_retry_policy(error, is_retryable):
    """A tunnel being negotiated comes back on its own; a setting that is off does not."""
    assert issubclass(error, RetryableError) is is_retryable


def test_the_forwarded_port_is_written_to_the_service(synchronizer, forwarder, service):
    forwarder.get_forwarded_port.return_value = FORWARDED_PORT

    synchronizer.synchronize()

    assert service.set_port.call_args_list == [call(FORWARDED_PORT)]


def test_every_run_writes_the_port_again(synchronizer, forwarder, service):
    """Nothing is remembered between runs: anything may have edited it since."""
    forwarder.get_forwarded_port.return_value = FORWARDED_PORT

    synchronizer.synchronize()
    synchronizer.synchronize()

    assert service.set_port.call_args_list == [call(FORWARDED_PORT)] * 2


def test_a_missing_port_is_never_written_to_the_service(synchronizer, service):
    """Writing a 0 would stop qBittorrent listening at all."""
    with pytest.raises(NoForwardedPortYet):
        synchronizer.synchronize()

    service.set_port.assert_not_called()


def test_a_missing_first_port_is_waited_for(synchronizer, clock):
    """Negotiating a tunnel takes a while, and reports no port all the way through."""
    for clock.now in (0.0, WAIT_FOR_FIRST_PORT / 2, WAIT_FOR_FIRST_PORT - 1):
        with pytest.raises(NoForwardedPortYet):
            synchronizer.synchronize()


def test_a_first_port_that_never_comes_is_given_up_on(synchronizer, clock):
    """Waiting forever hides the one thing that would explain it, the setting."""
    with pytest.raises(NoForwardedPortYet):
        synchronizer.synchronize()

    clock.now = WAIT_FOR_FIRST_PORT

    with pytest.raises(ForwardedPortNeverCame) as error:
        synchronizer.synchronize()
    assert "VPN_PORT_FORWARDING" in str(error.value)


def test_a_port_lost_after_the_deadline_is_only_a_renegotiation(
    synchronizer, forwarder, clock
):
    """A tunnel that dropped one port will get another, however late it is."""
    forwarder.get_forwarded_port.return_value = FORWARDED_PORT
    synchronizer.synchronize()

    forwarder.get_forwarded_port.return_value = None
    clock.now = WAIT_FOR_FIRST_PORT * 10

    # Fatal here would take the deployment down whenever the tunnel renegotiates.
    with pytest.raises(NoForwardedPortYet):
        synchronizer.synchronize()


def test_a_first_port_arriving_late_is_still_accepted(
    synchronizer, forwarder, service, clock
):
    """The deadline only ends the wait, it does not refuse what comes after."""
    forwarder.get_forwarded_port.return_value = FORWARDED_PORT
    clock.now = WAIT_FOR_FIRST_PORT * 10

    synchronizer.synchronize()

    assert service.set_port.call_args_list == [call(FORWARDED_PORT)]


def test_the_port_that_was_set_is_logged(synchronizer, forwarder, caplog):
    """The one line telling an operator the deployment is doing its job."""
    caplog.set_level(logging.INFO)
    forwarder.get_forwarded_port.return_value = FORWARDED_PORT

    synchronizer.synchronize()

    assert str(FORWARDED_PORT) in caplog.text
