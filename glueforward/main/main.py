import logging
import logging.config as logging_config
import signal
import sys
from enum import IntEnum
from os import getenv
from time import monotonic, sleep

from .errors import RetryableError
from .gluetun import GluetunClient
from .qbittorrent import QBittorrentClient
from .service_client import ServiceClient


class ReturnCodes(IntEnum):
    MISSING_ENVIRONMENT_VARIABLE = 1
    UNKNOWN_SERVICE_TYPE = 2
    UNRETRYABLE_EXCEPTION_IN_LIFECYCLE = 3
    INVALID_ENVIRONMENT_VARIABLE = 4

class Application:

    def __init__(self) -> None:
        self._configure_logging()
        self._retry_interval = self._integer_getenv("RETRY_INTERVAL", default=10)
        self._success_interval = self._integer_getenv("SUCCESS_INTERVAL", 60 * 5)
        self._gluetun = GluetunClient(
            url=self._required_getenv("GLUETUN_URL"),
            api_key=getenv("GLUETUN_API_KEY"),
            wait_for_port_until=monotonic()
            + self._integer_getenv("GLUETUN_PORT_WAIT_DURATION", 300),
        )
        self._service_client = self._create_service_client(
            service_type=self._required_getenv("SERVICE_TYPE")
        )

    def _required_getenv(self, name: str) -> str:
        """Get an environment variable or exit if it is not set"""
        if (value := getenv(name)) is None:
            logging.critical("Environment variable %s is required", name)
            sys.exit(ReturnCodes.MISSING_ENVIRONMENT_VARIABLE)
        return value

    def _integer_getenv(self, name: str, default: int) -> int:
        """Get a duration in seconds, or exit if it is not a whole number"""
        if (value := getenv(name)) is None:
            return default
        try:
            return int(value)
        except ValueError:
            logging.critical(
                "Environment variable %s must be an integer, got %r", name, value
            )
            sys.exit(ReturnCodes.INVALID_ENVIRONMENT_VARIABLE)

    def _create_service_client(self, service_type: str) -> ServiceClient:
        """Create and return the appropriate service client based on SERVICE_TYPE"""
        if service_type == "qbittorrent":
            return QBittorrentClient(
                url=self._required_getenv("QBITTORRENT_URL"),
                credentials={
                    "username": self._required_getenv("QBITTORRENT_USERNAME"),
                    "password": self._required_getenv("QBITTORRENT_PASSWORD"),
                },
            )
        logging.critical("Invalid SERVICE_TYPE: %s", service_type)
        sys.exit(ReturnCodes.UNKNOWN_SERVICE_TYPE)

    @staticmethod
    def _configure_logging() -> None:
        """Configure logging from the LOG_LEVEL environment variable"""
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

    def _loop(self) -> None:
        """Function called in a loop to check for changes in the forwarded port"""
        forwarded_port = self._gluetun.get_forwarded_port()
        self._service_client.set_port(forwarded_port)
        logging.info("Listening port set to %d", forwarded_port)

    def run(self) -> None:
        """App entry point, in charge of starting the loop"""
        while True:
            try:
                self._loop()
            except RetryableError as error:
                logging.error("Retryable error in lifecycle", exc_info=error)
                if error.get_retry_immediately():
                    logging.info("Retrying immediately")
                else:
                    logging.info("Retrying in %d seconds", self._retry_interval)
                    sleep(self._retry_interval)
            except Exception as error:  # pylint: disable=broad-exception-caught
                logging.critical("Unretryable error in lifecycle", exc_info=error)
                sys.exit(ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE)
            else:
                sleep(self._success_interval)


def handle_sigterm(*_: object) -> None:
    """Shut down on SIGTERM, the signal a container is stopped with.

    Without a handler the kernel never delivers it to PID 1, so `docker stop`
    waits out its whole timeout before resorting to SIGKILL.
    """
    logging.info("Received SIGTERM, shutting down")
    sys.exit(0)


def main() -> None:
    """Run the application."""
    signal.signal(signal.SIGTERM, handle_sigterm)
    Application().run()
