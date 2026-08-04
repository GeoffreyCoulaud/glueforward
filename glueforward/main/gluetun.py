import logging
from typing import TypedDict

import httpx

from .errors import RetryableError

# What gluetun's control server answers for as long as no port is forwarded.
NO_FORWARDED_PORT = 0


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


class GluetunUnexpectedResponse(Exception):
    """Exception raised when the answer cannot have come from gluetun"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Unexpected answer from gluetun. "
            "Check that GLUETUN_URL points to its control server.",
        )


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:
    """gluetun's control server, seen through the one endpoint we call.

    Translates HTTP into either a port or an error, and decides nothing:
    what a missing port means is the caller's to judge.
    """

    _client: httpx.Client

    def __init__(self, url: str, api_key: None | str):
        self._client = httpx.Client(base_url=url)
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

    def get_forwarded_port(self) -> int | None:
        """Return the forwarded port, or None while gluetun has none."""
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
        return None if port == NO_FORWARDED_PORT else port
