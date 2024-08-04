from enum import IntEnum
from os import getenv
from time import sleep

from gluetun import GluetunClient, GluetunGetFwPortFailed
from qbittorrent import (
    QbittorrentAuthFailed,
    QBittorrentClient,
    QbittorrentSetPortFailed,
)


class ReturnCodes(IntEnum):
    MISSING_ENV_VARS = 1
    QBITTORRENT_AUTH_ERROR = 2


def getenv_mandatory(name: str) -> str:
    """Get an environment variable or exit if it is not set"""
    if (value := getenv(name)) is None:
        print(f"{name} environment variable is required")
        exit(ReturnCodes.MISSING_ENV_VARS)
    return value


def main():

    gluetun_client = GluetunClient(url=getenv_mandatory("GLUETUN_URL"))
    qbittorrent_client = QBittorrentClient(url=getenv_mandatory("QBITTORRENT_URL"))
    try:
        qbittorrent_client.authenticate(
            username=getenv_mandatory("QBITTORRENT_USERNAME"),
            password=getenv_mandatory("QBITTORRENT_PASSWORD"),
        )
    except QbittorrentAuthFailed as e:
        print(f"Failed to authenticate to qbittorrent: {e}")
        exit(ReturnCodes.QBITTORRENT_AUTH_ERROR)

    # Periodically check the port number from gluetun
    # If an error occurs, retry after a shorter interval
    # All intervals are in seconds
    success_interval = getenv("SUCCESS_INTERVAL", 60 * 5)
    retry_interval = getenv("RETRY_INTERVAL", 10)
    while True:
        sleep_amount = success_interval
        last_known_port = None
        try:
            port = gluetun_client.get_forwarded_port()
            if port == last_known_port:
                continue
            last_known_port = port
            qbittorrent_client.set_port(port)
        except Exception as e:
            sleep_amount = retry_interval
            match e:
                case GluetunGetFwPortFailed():
                    print(f"Failed to get forwarded port from gluetun: {e}")
                case QbittorrentSetPortFailed():
                    print(f"Failed to set port in qbittorrent: {e}")
                case _:
                    raise e
        sleep(sleep_amount)


if __name__ == "__main__":
    main()
