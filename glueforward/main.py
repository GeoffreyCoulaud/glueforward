import logging
import logging.config as logging_config
import sys
from enum import IntEnum
from os import getenv
from time import sleep
from typing import cast

from errors import RetryableGlueforwardError
from gluetun import GluetunClient
from qbittorrent import QBittorrentAuthFailed, QBittorrentClient
from slskd import SlskdClient, SlskdAuthFailed
from service_client import ServiceClient


class ReturnCodes(IntEnum):
    MISSING_ENVIRONMENT_VARIABLE = 1
    SERVICE_CLIENT_AUTHENTICATION_ERROR = 2


class Application:

    __gluetun: GluetunClient
    __service_client: ServiceClient
    __success_interval: int
    __retry_interval: int

    def __required_getenv(self, name: str) -> str:
        """Get an environment variable or exit if it is not set"""
        if (value := getenv(name)) is None:
            logging.critical("Environment variable %s is required", name)
            sys.exit(ReturnCodes.MISSING_ENVIRONMENT_VARIABLE)
        return value

    def __optional_getenv(self, name: str, default: str | None = None) -> str | None:
        """Get an environment variable or warn if it is not set"""
        if (value := getenv(name)) is None:
            logging.warning("Environment variable %s is not defined", name)
            return default
        return value

    def __create_service_client(self) -> ServiceClient:
        """Create and return the appropriate service client based on SERVICE_TYPE"""

        # Since we pass a default value, we can safely cast to str
        service_type = cast(
            str, self.__optional_getenv("SERVICE_TYPE", "qbittorrent")
        ).lower()

        if service_type == "qbittorrent":
            return QBittorrentClient(
                url=self.__required_getenv("QBITTORRENT_URL"),
                credentials={
                    "username": self.__required_getenv("QBITTORRENT_USERNAME"),
                    "password": self.__required_getenv("QBITTORRENT_PASSWORD"),
                },
            )
        if service_type == "slskd":
            return SlskdClient(
                url=self.__required_getenv("SLSKD_URL"),
                credentials={
                    "username": self.__required_getenv("SLSKD_USERNAME"),
                    "password": self.__required_getenv("SLSKD_PASSWORD"),
                },
            )
        logging.critical(
            "Invalid SERVICE_TYPE: %s. Must be 'qbittorrent' or 'slskd'", 
            service_type
        )
        sys.exit(ReturnCodes.MISSING_ENVIRONMENT_VARIABLE)

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
        self.__retry_interval = int(getenv("RETRY_INTERVAL", str(10)))
        self.__success_interval = int(getenv("SUCCESS_INTERVAL", str(60 * 5)))
        self.__gluetun = GluetunClient(
            url=self.__required_getenv("GLUETUN_URL"),
            api_key=self.__optional_getenv("GLUETUN_API_KEY")
        )
        self.__service_client = self.__create_service_client()

    def _loop(self) -> None:
        """Function called in a loop to check for changes in the forwarded port"""
        forwarded_port = self.__gluetun.get_forwarded_port()
        self.__service_client.set_port(forwarded_port)
        logging.info("Listening port set to %d", forwarded_port)

    def run(self) -> None:
        """App entry point, in charge of setting up the app and starting the loop"""
        self._setup()
        while True:
            try:
                self._loop()
            except (QBittorrentAuthFailed, SlskdAuthFailed) as error:
                logging.critical(
                    "Could not authenticate to service (%s)",
                    self.__service_client.get_service_name(),
                    exc_info=error,
                )
                sys.exit(ReturnCodes.SERVICE_CLIENT_AUTHENTICATION_ERROR)
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
