import logging
from typing import TypedDict

import httpx

from .errors import RetryableError


class GluetunAuthFailed(Exception):
    """Exception raised when gluetun authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Failed to authenticate to Gluetun. See https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md",  # pylint: disable=line-too-long
        )


class GluetunUnreachable(RetryableError):
    """Exception raised when gluetun is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to reach gluetun")


class GluetunServerError(RetryableError):
    """Exception raised when gluetun returns a 5xx error"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Internal gluetun server error")


class GluetunNoForwardedPort(RetryableError):
    """Exception raised when gluetun has no port forwarded yet"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Gluetun has no forwarded port yet")


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:
    _client: httpx.Client

    def __init__(self, url: str, api_key: None | str):
        self._client = httpx.Client(base_url=url)
        if api_key:
            self._client.headers.update({"X-API-Key": api_key})
        logging.debug("Gluetun client created with base url %s", url)

    def get_forwarded_port(self) -> int:
        try:
            response = self._client.get(url="/v1/portforward")
            response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException) as exception:
            raise GluetunUnreachable(self._client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            if exception.response.status_code == 401:
                raise GluetunAuthFailed(exception.response.text) from exception
            raise GluetunServerError(
                exception.response.status_code,
                exception.response.text,
            ) from exception
        data: _PortForwardedResponseModel = response.json()
        if (port := data["port"]) == 0:
            # What gluetun reports until the tunnel has been given a port.
            raise GluetunNoForwardedPort()
        return port
