import logging
from typing import TypedDict

import httpx

from errors import RetryableGlueforwardError


class GluetunUnreachable(RetryableGlueforwardError):
    """Exception raised when gluetun is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to reach gluetun")


class GluetunGetForwardedPortFailed(RetryableGlueforwardError):
    """Exception raised when getting port forwarded fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to get gluetun forwarded port")


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:

    __client: httpx.Client

    def __init__(self, url: str):
        self.__client = httpx.Client(base_url=url)
        logging.debug("Gluetun client created with base url %s", url)

    def get_forwarded_port(self) -> int:
        try:
            response = self.__client.get(url="/v1/openvpn/portforwarded")
            response.raise_for_status()
        except httpx.ConnectError as exception:
            raise GluetunUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            raise GluetunGetForwardedPortFailed(
                exception.response.status_code,
                exception.response.text,
            ) from exception
        data: _PortForwardedResponseModel = response.json()
        return data["port"]
