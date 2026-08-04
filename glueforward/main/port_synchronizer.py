import logging

from .errors import RetryableError
from .ports import Clock, PortForwarder, ServiceClient


class NoForwardedPortYet(RetryableError):
    """Exception raised while the VPN has no port forwarded"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "The VPN has no forwarded port yet")


class ForwardedPortNeverCame(Exception):
    """Exception raised when a first forwarded port never arrived in time"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Gluetun still reports no forwarded port. "
            "Check that VPN_PORT_FORWARDING is on, and that your VPN provider and "
            "server support port forwarding.",
        )


class PortSynchronizer:
    """Keeps the service listening on whichever port the VPN forwards.

    Nothing is remembered between two runs: the port is written afresh every
    time, since anything may have edited it since.
    """

    def __init__(
        self,
        forwarder: PortForwarder,
        service: ServiceClient,
        clock: Clock,
        wait_for_first_port_duration: float,
    ) -> None:
        self._forwarder = forwarder
        self._service = service
        self._clock = clock
        self._wait_for_first_port_until = (
            clock.monotonic() + wait_for_first_port_duration
        )
        self._has_ever_forwarded_port = False

    def _get_error_for_missing_port(self) -> Exception:
        """Tell a tunnel still being negotiated from one that never will be.

        Waiting forever on the latter hides the one thing that would explain
        it, the setting; giving up on the former takes a healthy deployment
        down every time its tunnel renegotiates.
        """
        if self._has_ever_forwarded_port:
            return NoForwardedPortYet()
        if self._clock.monotonic() >= self._wait_for_first_port_until:
            return ForwardedPortNeverCame()
        return NoForwardedPortYet()

    def synchronize(self) -> None:
        port = self._forwarder.get_forwarded_port()
        if port is None:
            raise self._get_error_for_missing_port()
        self._has_ever_forwarded_port = True
        self._service.set_port(port)
        logging.info("Listening port set to %d", port)
