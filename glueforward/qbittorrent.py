import httpx


class QbittorrentAuthFailed(Exception):
    """Exception raised when qbittorrent authentication fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to authenticate to qBittorrent", *args)


class QbittorrentSetPortFailed(Exception):
    """Exception raised when qbittorrent port setting fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to set qBittorrent listening port", *args)


class QbittorrentClient:

    __client: httpx.Client

    def __init__(self, url: str):
        self.__client = httpx.Client(base_url=url)

    def authenticate(self, username: str, password: str) -> None:
        res = self.__client.post(
            url="/api/v2/auth/login",
            cookies=None,
            data={"username": username, "password": password},
        )
        if res.status_code != httpx.codes.OK:
            raise QbittorrentAuthFailed(f"${res.status_code} {res.text}")
        self.__client.cookies = res.cookies

    def set_port(self, port: int) -> None:
        res = self.__client.post(
            "/api/v2/app/setPreferences",
            data={
                "listen_port": port,
                "random_port": False,
                "upnp": False,
            },
        )
        if res.status_code != httpx.codes.OK:
            raise QbittorrentSetPortFailed(f"${res.status_code} {res.text}")
        return
