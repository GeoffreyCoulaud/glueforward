import httpx


class QbittorrentAuthFailed(Exception):
    """Exception raised when qbittorrent authentication fails"""


class QbittorrentSetPortFailed(Exception):
    """Exception raised when qbittorrent port setting fails"""


class QbittorrentClient:

    __url: str
    __cookies: httpx.Cookies

    def __init__(self, url: str):
        self.__url = url

    def authenticate(self, username: str, password: str) -> None:
        url = f"{self.__url}/api/v2/auth/login"
        response = httpx.post(url, data={"username": username, "password": password})
        if response.status_code != httpx.codes.OK:
            raise QbittorrentAuthFailed(f"${response.status_code} {response.text}")
        self.__cookies = response.cookies

    def set_port(self, port: int) -> None:
        url = f"{self.__url}/api/v2/app/setPreferences"
        request_data = {
            "listen_port": port,
            "random_port": False,
            "upnp": False,
        }
        response = httpx.post(url, json=request_data, cookies=self.__cookies)
        if response.status_code != httpx.codes.OK:
            raise QbittorrentSetPortFailed(f"${response.status_code} {response.text}")
        return
