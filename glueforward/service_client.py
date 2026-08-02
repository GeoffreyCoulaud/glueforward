from typing import Protocol


class ServiceClient(Protocol):
    def set_port(self, port: int) -> None: ...
