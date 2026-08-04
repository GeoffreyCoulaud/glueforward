import logging
from time import monotonic
from typing import TypedDict

import httpx

from .errors import RetryableError


class GluetunAuthFailed(Exception):
    """Exception raised when gluetun authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Failed to authenticate to Gluetun. "
            "See https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/"
            "control-server.md",
        )


class GluetunUnreachable(RetryableError):
    """Exception raised when gluetun is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Failed to reach gluetun")


class GluetunServerError(RetryableError):
    """Exception raised when gluetun returns a 5xx error"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Internal gluetun server error")


class GluetunNoForwardedPort(RetryableError):
    """Exception raised when gluetun has no port forwarded yet"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Gluetun has no forwarded port yet")


class GluetunUnexpectedResponse(Exception):
    """Exception raised when the answer cannot have come from gluetun"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Unexpected answer from gluetun. "
            "Check that GLUETUN_URL points to its control server.",
        )


class GluetunFailedToForwardPort(Exception):
    """Exception raised when Gluetun fails to obtain a port after some time"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Gluetun still reports no forwarded port. "
            "Check that VPN_PORT_FORWARDING is on, and that your VPN provider and "
            "server support port forwarding.",
        )


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:
    _client: httpx.Client
    _has_ever_forwarded_port: bool
    _wait_for_port_until: float

    def __init__(self, url: str, api_key: None | str, wait_for_port_until: float):
        self._client = httpx.Client(base_url=url)
        self._wait_for_port_until = wait_for_port_until
        if api_key:
            self._client.headers.update({"X-API-Key": api_key})
        logging.debug("Gluetun client created with base url %s", url)

    @staticmethod
    def _get_error_for_status(exception: httpx.HTTPStatusError) -> Exception:
        status_code = exception.response.status_code
        text = exception.response.text
        if status_code == 401:
            return GluetunAuthFailed(text)
        if status_code >= 500:
            return GluetunServerError(status_code, text)
        # Anything else is gluetun answering out of character, or not gluetun.
        return GluetunUnexpectedResponse(status_code, text)

    def get_forwarded_port(self) -> int:
        try:
            response = self._client.get(url="/v1/portforward")
            response.raise_for_status()
        except (httpx.NetworkError, httpx.TimeoutException) as exception:
            raise GluetunUnreachable(self._client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            raise self._get_error_for_status(exception) from exception
        try:
            data: _PortForwardedResponseModel = response.json()
            port = data["port"]
        except (ValueError, KeyError, TypeError) as exception:
            raise GluetunUnexpectedResponse(response.text[:200]) from exception
        if port == 0:
            # Gluetun returns 0 when no port is forwarded.
            # We need to distinguish a temporary drop from a misconfiguration.
            if self._has_ever_forwarded_port:
                raise GluetunNoForwardedPort()
            if monotonic() >= self._wait_for_port_until:
                raise GluetunFailedToForwardPort()
        self._has_ever_forwarded_port = True
        return port
