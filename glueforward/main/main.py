import logging
import logging.config as logging_config
import signal
import sys
from os import getenv

from .application import Application
from .clock import SystemClock
from .config import Config, ConfigurationError, get_configuration
from .errors import ReturnCodes
from .gluetun import GluetunClient
from .port_synchronizer import PortSynchronizer
from .ports import ServiceClient
from .qbittorrent import QBittorrentClient


def configure_logging() -> None:
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


def build_service_client(config: Config) -> ServiceClient:
    """Create the client of the one service the configuration names."""
    return QBittorrentClient(
        url=config.service.url,
        credentials={
            "username": config.service.username,
            "password": config.service.password,
        },
    )


def handle_sigterm(*_: object) -> None:
    """Shut down on SIGTERM, the signal a container is stopped with.

    Without a handler the kernel never delivers it to PID 1, so `docker stop`
    waits out its whole timeout before resorting to SIGKILL.
    """
    logging.info("Received SIGTERM, shutting down")
    sys.exit(0)


def main() -> None:
    """Run the application, and turn whatever stops it into an exit code."""
    signal.signal(signal.SIGTERM, handle_sigterm)
    configure_logging()
    try:
        config = get_configuration()
        clock = SystemClock()
        Application(
            synchronizer=PortSynchronizer(
                forwarder=GluetunClient(
                    url=config.gluetun_url,
                    api_key=config.gluetun_api_key,
                ),
                service=build_service_client(config),
                clock=clock,
                wait_for_first_port_duration=config.gluetun_port_wait_duration,
            ),
            clock=clock,
            retry_interval=config.retry_interval,
            success_interval=config.success_interval,
        ).run()
    except ConfigurationError as error:
        logging.critical("%s", error)
        sys.exit(error.return_code)
    except Exception as error:  # pylint: disable=broad-exception-caught
        logging.critical("Unretryable error in lifecycle", exc_info=error)
        sys.exit(ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE)
