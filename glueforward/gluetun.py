from typing import TypedDict

import httpx


class GluetunGetFwPortFailed(Exception):
    """Exception raised when getting port forwarded fails"""

    def __init__(self, *args: object) -> None:
        super().__init__("Failed to get gluetun forwarded port", *args)


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:

    __client: httpx.Client

    def __init__(self, url: str):
        self.__client = httpx.Client(base_url=url)

    def get_forwarded_port(self) -> int:
        res = self.__client.get(url="/v1/openvpn/portforwarded")
        if res.status_code != httpx.codes.OK:
            raise GluetunGetFwPortFailed(f"{res.status_code} {res.text}")
        data: _PortForwardedResponseModel = res.json()
        return data["port"]
