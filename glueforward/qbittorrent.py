import json
import logging

import httpx


class QBittorrentAuthFailed(Exception):
    """Exception raised when qbittorrent authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to authenticate to qBittorrent", *args)


class QBittorrentSetPortFailed(Exception):
    """Exception raised when qbittorrent port setting fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to set qBittorrent listening port", *args)


class QBittorrentUnreachable(Exception):
    """Exception raised when qbittorrent is unreachable"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to reach qBittorrent", *args)


class QBittorrentClient:

    __client: httpx.Client
    __credentials: dict[str, str]

    def __init__(self, url: str, credentials: dict[str, str]):
        self.__credentials = credentials
        self.__client = httpx.Client(base_url=url)
        logging.debug("qBittorrent client created with base url %s", url)

    def get_is_authenticated(self) -> bool:
        return len(self.__client.cookies) > 0

    def __authenticate(self) -> None:
        if self.get_is_authenticated():
            return
        try:
            response = self.__client.post(
                url="/api/v2/auth/login",
                data=self.__credentials,
                cookies=None,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exception:
            raise QBittorrentAuthFailed(
                exception.response.status_code,
                exception.response.text,
            ) from exception
        logging.debug("qBittorrent client authenticated")
        self.__client.cookies.update(response.cookies)

    def __reset_authentication(self) -> None:
        self.__client.cookies.clear()
        logging.debug("qBittorrent client authentication reset")

    def set_port(self, port: int) -> None:
        if not self.get_is_authenticated():
            self.__authenticate()
        try:
            data = json.dumps(
                {
                    "listen_port": port,
                    "random_port": False,
                    "upnp": False,
                }
            )
            response = self.__client.post(
                "/api/v2/app/setPreferences",
                data={"json": data},
            )
            response.raise_for_status()
        except httpx.ConnectError as exception:
            raise QBittorrentUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            if exception.response.status_code == 403:
                self.__reset_authentication()
                raise QBittorrentAuthFailed(
                    exception.response.status_code,
                    exception.response.text,
                ) from exception
            raise QBittorrentSetPortFailed(
                exception.response.status_code,
                exception.response.text,
            ) from exception
