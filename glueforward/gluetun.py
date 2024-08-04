from datetime import datetime
from typing import TypedDict

import httpx


class GluetunGetFwPortFailed(Exception):
    """Exception raised when getting port forwarded fails"""


class _PortForwardedResponseModel(TypedDict):
    port: int


class GluetunClient:

    __url: str

    def __init__(self, url: str):
        self.__url = url

    def get_forwarded_port(self) -> int:
        response = httpx.get(f"{self.__url}/v1/openvpn/portforwarded")
        if response.status_code != httpx.codes.OK:
            raise GluetunGetFwPortFailed(f"{response.status_code} {response.text}")
        data: _PortForwardedResponseModel = response.json()
        return data["port"]
