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

    def __post(self, url: str, data: dict[str, str]) -> httpx.Response:
        """
        Send a POST request to the qBittorrent API, handling some exceptions

        May raise
        - QBittorrentUnreachable
        - QBittorrentAuthFailed
        - httpx.HTTPStatusError
        """
        try:
            response = self.__client.post(url, data=data)
            response.raise_for_status()
            return response
        except httpx.ConnectError as exception:
            raise QBittorrentUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            # Special case, auth error
            if exception.response.status_code == 403:
                self.__reset_authentication()
                raise QBittorrentAuthFailed(
                    exception.response.status_code,
                    exception.response.text,
                ) from exception
            # Otherwise, raise generic exception
            raise exception

    def __authenticate(self) -> None:
        if self.get_is_authenticated():
            return
        response = self.__post(
            url="/api/v2/auth/login",
            data=self.__credentials,
        )
        logging.debug("qBittorrent client authenticated")
        self.__client.cookies.update(response.cookies)

    def __reset_authentication(self) -> None:
        self.__client.cookies.clear()
        logging.debug("qBittorrent client authentication reset")

    def set_port(self, port: int) -> None:
        if not self.get_is_authenticated():
            self.__authenticate()
        data = {
            "listen_port": port,
            "random_port": False,
            "upnp": False,
        }
        try:
            self.__post(
                url="/api/v2/app/setPreferences",
                data={"json": json.dumps(data)},
            )
        except httpx.HTTPStatusError as exception:
            # Handle 5xx errors (= qbt has an issue)
            if exception.response.status_code // 100 == 5:
                raise QBittorrentSetPortFailed(
                    exception.response.status_code,
                    exception.response.text,
                ) from exception
            # Otherwise, raise generic exception
            raise exception
