from typing import TypedDict

import httpx


class GluetunUnreachable(Exception):
    """Exception raised when gluetun is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to reach gluetun", *args)


class GluetunGetForwardedwPortFailed(Exception):
    """Exception raised when getting port forwarded fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to get gluetun forwarded port", *args)


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:

    __client: httpx.Client

    def __init__(self, url: str):
        self.__client = httpx.Client(base_url=url)

    def get_forwarded_port(self) -> int:
        try:
            response = self.__client.get(url="/v1/openvpn/portforwarded")
            response.raise_for_status()
        except httpx.ConnectError as exception:
            raise GluetunUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            raise GluetunGetForwardedwPortFailed(
                exception.response.status_code,
                exception.response.text,
            ) from exception
        data: _PortForwardedResponseModel = response.json()
        return data["port"]
