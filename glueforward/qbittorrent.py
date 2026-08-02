import json
import logging

import httpx

from .errors import RetryableError
from .service_client import ServiceClient


class QBittorrentServerError(RetryableError):
    """Exception raised when qbittorrent returns a 5xx error"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Internal qBittorrent server error")


class QBittorrentUnreachable(RetryableError):
    """Exception raised when qbittorrent is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to reach qBittorrent")


class QBittorrentForbiddenError(Exception):
    """Exception raised when qbittorrent authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            "Failed to authenticate to qBittorrent.",
            "Check your credentials, as they may be incorrect.",
        )


class QBittorrentAuthenticationNeeded(RetryableError):
    """Exception raised when qbittorrent needs authentication"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            message="qBittorrent needs authentication",
            retry_immediately=True,  # Reauthenticating is immediate
        )


class QBittorrentClient(ServiceClient):

    __client: httpx.Client
    __credentials: dict[str, str]

    def __init__(self, url: str, credentials: dict[str, str]):
        self.__credentials = credentials
        self.__client = httpx.Client(base_url=url)
        logging.debug("qBittorrent client created with base url %s", url)

    def __get_is_authenticated(self) -> bool:
        return len(self.__client.cookies) > 0

    def __authenticate(self) -> None:
        logging.debug("Authenticating to qBittorrent")
        try:
            response = self.__client.post(
                url="/api/v2/auth/login",
                data=self.__credentials,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exception:
            if exception.response.status_code == 403:
                raise QBittorrentForbiddenError from exception
            raise QBittorrentServerError from exception
        self.__client.cookies.update(response.cookies)
        logging.debug("qBittorrent client authenticated")

    def __reset_authentication(self) -> None:
        self.__client.cookies.clear()
        logging.debug("qBittorrent client authentication reset")

    def set_port(self, port: int) -> None:
        if not self.__get_is_authenticated():
            self.__authenticate()
        data = {"listen_port": port, "random_port": False, "upnp": False}
        try:
            response = self.__client.post(
                url="/api/v2/app/setPreferences",
                data={"json": json.dumps(data)},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exception:
            if exception.response.status_code == 401:
                # If failed here, we were authenticated before but the session expired,
                # so we need to reauthenticate and retry.
                logging.warning("qBittorrent session expired")
                self.__reset_authentication()
                raise QBittorrentAuthenticationNeeded from exception
            raise exception
        logging.info("Successfully set qBittorrent port")