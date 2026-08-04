from typing import Protocol


class Clock(Protocol):
    """The passage of time, as the application observes it and waits on it."""

    def monotonic(self) -> float: ...

    def sleep(self, duration: float) -> None: ...


class PortForwarder(Protocol):
    """The VPN side of the deployment, which forwards a port to listen on.

    `get_forwarded_port` answers None for as long as no port is forwarded,
    which is what every deployment starts with while its tunnel is negotiated.
    """

    def get_forwarded_port(self) -> int | None: ...


class ServiceClient(Protocol):
    """The application whose listening port is kept in sync with the VPN's."""

    def set_port(self, port: int) -> None: ...
