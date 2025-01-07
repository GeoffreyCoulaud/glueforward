import logging
from typing import TypedDict, Union

import httpx

from errors import GlueforwardError, RetryableGlueforwardError


class GluetunAuthFailed(GlueforwardError):
    """Exception raised when gluetun authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to authenticate to Gluetun. See https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md")


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
    __credentials: dict[str, str]

    def __init__(self, url: str, api_key: str = ''):
        self.__api_key = api_key
        self.__client = httpx.Client(base_url=url)
        logging.debug("Gluetun client created with base url %s", url)

    def get_has_credentials(self) -> bool:
        return len(self.__api_key) > 0

    def get_forwarded_port(self) -> int:

        try:
            if self.get_has_credentials():
                response = self.__client.request(method='GET', url="/v1/openvpn/portforwarded", headers={"X-API-Key": self.__api_key})
            else:
                response = self.__client.request(method='GET', url="/v1/openvpn/portforwarded")
            if response.status_code == 401:
                raise GluetunAuthFailed()
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
