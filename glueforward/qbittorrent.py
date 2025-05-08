import json
import logging
from typing import Optional

import httpx

from errors import GlueforwardError, RetryableGlueforwardError
from service_client import ServiceClient


class QBittorrentAuthFailed(GlueforwardError):
    """Exception raised when qbittorrent authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to authenticate to qBittorrent")


class QBittorrentSetPortFailed(RetryableGlueforwardError):
    """Exception raised when qbittorrent port setting fails"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to set qBittorrent listening port")


class QBittorrentUnreachable(RetryableGlueforwardError):
    """Exception raised when qbittorrent is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to reach qBittorrent")


class QBittorrentReauthNeeded(RetryableGlueforwardError):
    """Exception raised when qbittorrent needs reauthentication"""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            message="qBittorrent needs reauthentication",
            retry_immediately=True,  # Reauthenticating is immediate
        )


class QBittorrentClient(ServiceClient):

    __client: httpx.Client
    __credentials: dict[str, str]

    def __init__(self, url: str, credentials: dict[str, str]):
        self.__credentials = credentials
        self.__client = httpx.Client(base_url=url)
        logging.debug("qBittorrent client created with base url %s", url)

    def get_is_authenticated(self) -> bool:
        return len(self.__client.cookies) > 0

    def __request(self, method: str, url: str, data: dict[str, str]) -> Optional[httpx.Response]:
        """
        Send a POST request to the qBittorrent API, handling some exceptions

        May raise
        - QBittorrentUnreachable
        - QBittorrentAuthFailed
        - httpx.HTTPStatusError
        """
        try:
            response = self.__client.request(method=method, url=url, data=data)
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.ReadTimeout) as exception:
            raise QBittorrentUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            self._handle_request_exception(
                exception,
                QBittorrentAuthFailed,
                QBittorrentSetPortFailed
            )
            return None

    def authenticate(self) -> None:
        if self.get_is_authenticated():
            return
        logging.debug("Authenticating to qBittorrent")
        response = self.__request(
            method="post",
            url="/api/v2/auth/login",
            data=self.__credentials,
        )
        logging.debug("qBittorrent client authenticated")
        self.__client.cookies.update(response.cookies)

    def reset_authentication(self) -> None:
        self.__client.cookies.clear()
        logging.debug("qBittorrent client authentication reset")

    def set_port(self, port: int) -> None:
        if not self.get_is_authenticated():
            self.authenticate()
        data = {
            "listen_port": port,
            "random_port": False,
            "upnp": False,
        }
        try:
            self.__request(
                method="post",
                url="/api/v2/app/setPreferences",
                data={"json": json.dumps(data)},
            )
        except QBittorrentAuthFailed as exception:
            # If failed here, we were already authenticated before but session expired,
            # so we need to reauthenticate and retry.
            logging.warning("qBittorrent session expired, reauthenticating")
            self.reset_authentication()
            raise QBittorrentReauthNeeded() from exception
        except httpx.HTTPStatusError as exception:
            # Handle 5xx errors (= qbt has an issue)
            if exception.response.status_code // 100 == 5:
                raise QBittorrentSetPortFailed(
                    exception.response.status_code,
                    exception.response.text,
                ) from exception
            # Otherwise, raise generic exception
            raise exception
