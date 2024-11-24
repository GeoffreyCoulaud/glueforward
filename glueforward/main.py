import logging
import logging.config as logging_config
import sys
from enum import IntEnum
from os import getenv
from time import sleep

from errors import RetryableGlueforwardError
from gluetun import GluetunClient
from qbittorrent import QBittorrentAuthFailed, QBittorrentClient


class ReturnCodes(IntEnum):
    MISSING_ENVIRONMENT_VARIABLE = 1
    QBITTORRENT_AUTHENTICATION_ERROR = 2


class Application:

    __gluetun: GluetunClient
    __qbittorrent: QBittorrentClient
    __success_interval: int
    __retry_interval: int
    __last_set_port: int | None

    def __mgetenv(self, name: str) -> str:
        """Get an environment variable or exit if it is not set"""
        if (value := getenv(name)) is None:
            logging.critical("Environment variable %s is required", name)
            sys.exit(ReturnCodes.MISSING_ENVIRONMENT_VARIABLE)
        return value

    def _setup(self) -> None:
        """Setup the application"""

        # Configure logging
        log_level = (
            environment_log_level
            if (environment_log_level := getenv("LOG_LEVEL"))
            in logging.getLevelNamesMapping()
            else "INFO"
        )
        logging_config.dictConfig(
            {
                "version": 1,
                "formatters": {
                    "default": {
                        "format": "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
                    },
                },
                "loggers": {
                    "httpx": {
                        # Silence httpx logs, unless the log level is DEBUG
                        "level": "DEBUG" if log_level == "DEBUG" else "WARNING",
                    },
                },
                "root": {
                    "level": log_level,
                },
            }
        )
        logging.basicConfig(
            level=log_level, format="%(asctime)s [%(levelname)s] %(message)s"
        )

        # Initialize the state
        self.__last_set_port = None
        self.__retry_interval = int(getenv("RETRY_INTERVAL", str(10)))
        self.__success_interval = int(getenv("SUCCESS_INTERVAL", str(60 * 5)))
        self.__gluetun = GluetunClient(url=self.__mgetenv("GLUETUN_URL"))
        self.__qbittorrent = QBittorrentClient(
            url=self.__mgetenv("QBITTORRENT_URL"),
            credentials={
                "username": self.__mgetenv("QBITTORRENT_USERNAME"),
                "password": self.__mgetenv("QBITTORRENT_PASSWORD"),
            },
        )

    def _loop(self) -> None:
        """Function called in a loop to check for changes in the forwarded port"""
        forwarded_port = self.__gluetun.get_forwarded_port()
        if forwarded_port == self.__last_set_port:
            logging.info("Forwarded port hasn't changed")
            return
        # If setting the port fails, we want to retry even it didn't change on gluetun
        self.__last_set_port = None
        self.__qbittorrent.set_port(forwarded_port)
        self.__last_set_port = forwarded_port
        logging.info("Listening port set to %d", forwarded_port)

    def run(self) -> None:
        """App entry point, in charge of setting up the app and starting the loop"""
        self._setup()
        while True:
            try:
                self._loop()
            except QBittorrentAuthFailed as error:
                logging.critical(
                    "Could not authenticate to qBittorrent",
                    exc_info=error,
                )
                sys.exit(ReturnCodes.QBITTORRENT_AUTHENTICATION_ERROR)
            except RetryableGlueforwardError as error:
                logging.error("Retryable error in lifecycle", exc_info=error)
                if error.get_retry_immediately():
                    logging.info("Retrying immediately")
                else:
                    logging.info("Retrying in %d seconds", self.__retry_interval)
                    sleep(self.__retry_interval)
            else:
                sleep(self.__success_interval)


if __name__ == "__main__":
    Application().run()
