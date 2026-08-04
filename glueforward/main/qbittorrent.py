import json
import logging

import httpx

from .errors import RetryableError
from .service_client import ServiceClient


class QBittorrentServerError(RetryableError):
    """Exception raised when qbittorrent returns a 5xx error"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Internal qBittorrent server error")


class QBittorrentUnreachable(RetryableError):
    """Exception raised when qbittorrent is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Failed to reach qBittorrent")


class QBittorrentInvalidCredentials(Exception):
    """Exception raised when qbittorrent rejects the configured credentials"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Failed to authenticate to qBittorrent. "
            "Check your credentials, as they may be incorrect.",
        )


class QBittorrentBanned(Exception):
    """Exception raised when qbittorrent has banned us after failed logins"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, "Banned by qBittorrent after too many auth failures")


class QBittorrentUnexpectedResponse(Exception):
    """Exception raised when the answer cannot have come from qBittorrent"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Unexpected answer from qBittorrent. ",
            "Check that QBITTORRENT_URL points to its WebUI.",
        )


class QBittorrentAuthenticationNeeded(RetryableError):
    """Exception raised when qbittorrent needs authentication"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "qBittorrent needs authentication",
            retry_immediately=True,  # Reauthenticating is immediate
        )


class QBittorrentClient(ServiceClient):

    _client: httpx.Client
    _credentials: dict[str, str]

    def __init__(self, url: str, credentials: dict[str, str]):
        self._credentials = credentials
        self._client = httpx.Client(base_url=url)
        logging.debug("qBittorrent client created with base url %s", url)

    def _get_is_authenticated(self) -> bool:
        return len(self._client.cookies) > 0

    def _authenticate(self) -> None:
        logging.debug("Authenticating to qBittorrent")
        try:
            response = self._client.post(
                url="/api/v2/auth/login",
                data=self._credentials,
            )
            response.raise_for_status()
        except (httpx.NetworkError, httpx.TimeoutException) as exception:
            raise QBittorrentUnreachable(self._client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            status_code = exception.response.status_code
            if status_code == 401:
                raise QBittorrentInvalidCredentials() from exception
            if status_code == 403:
                raise QBittorrentBanned(exception.response.text) from exception
            if status_code >= 500:
                raise QBittorrentServerError() from exception
            raise QBittorrentUnexpectedResponse(status_code) from exception
        self._client.cookies.update(response.cookies)
        logging.debug("qBittorrent client authenticated")

    def _reset_authentication(self) -> None:
        self._client.cookies.clear()
        logging.debug("qBittorrent client authentication reset")

    def set_port(self, port: int) -> None:
        if not self._get_is_authenticated():
            self._authenticate()
        data = {"listen_port": port, "random_port": False, "upnp": False}
        try:
            response = self._client.post(
                url="/api/v2/app/setPreferences",
                data={"json": json.dumps(data)},
            )
            response.raise_for_status()
        except (httpx.NetworkError, httpx.TimeoutException) as exception:
            raise QBittorrentUnreachable(self._client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            status_code = exception.response.status_code
            if status_code == 403:
                # Authenticated earlier, so this is an expired session: renew it.
                logging.warning("qBittorrent session expired")
                self._reset_authentication()
                raise QBittorrentAuthenticationNeeded() from exception
            if status_code >= 500:
                raise QBittorrentServerError() from exception
            raise QBittorrentUnexpectedResponse(status_code) from exception
        logging.info("Successfully set qBittorrent port")
