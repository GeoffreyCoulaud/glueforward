import logging
from time import monotonic
from typing import TypedDict

import httpx

from .errors import RetryableError

# Long enough that a tunnel being negotiated is never called a mistake.
MISSING_PORT_WARNING_INTERVAL = 300


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


class GluetunUnexpectedResponse(Exception):
    """Exception raised when the answer cannot have come from gluetun"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Unexpected answer from gluetun.",
            "Check that GLUETUN_URL points to its control server.",
        )


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:
    _client: httpx.Client
    _missing_port_warning_due_at: None | float

    def __init__(self, url: str, api_key: None | str):
        self._client = httpx.Client(base_url=url)
        self._missing_port_warning_due_at = None
        if api_key:
            self._client.headers.update({"X-API-Key": api_key})
        logging.debug("Gluetun client created with base url %s", url)

    def _warn_if_the_port_is_taking_too_long(self) -> None:
        """Warn, at most every MISSING_PORT_WARNING_INTERVAL, that 0 is all we get.

        A tunnel that is still negotiating and one that will never forward a
        port report the very same 0, so only how long it lasts tells them apart.
        """
        now = monotonic()
        if self._missing_port_warning_due_at is None:
            self._missing_port_warning_due_at = now + MISSING_PORT_WARNING_INTERVAL
            return
        if now < self._missing_port_warning_due_at:
            return
        logging.warning(
            "Gluetun still reports no forwarded port. Check that VPN_PORT_FORWARDING "
            "is on, and that your VPN provider and server support port forwarding."
        )
        self._missing_port_warning_due_at = now + MISSING_PORT_WARNING_INTERVAL

    @staticmethod
    def _get_error_for_status(exception: httpx.HTTPStatusError) -> Exception:
        """Sort a status into one worth waiting out, and one worth stopping for."""
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
            # What gluetun reports until the tunnel has been given a port.
            self._warn_if_the_port_is_taking_too_long()
            raise GluetunNoForwardedPort()
        self._missing_port_warning_due_at = None
        return port
