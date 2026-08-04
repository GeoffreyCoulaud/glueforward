from dataclasses import dataclass
from os import getenv

from .errors import ReturnCodes

QBITTORRENT_SERVICE_TYPE = "qbittorrent"


class ConfigurationError(Exception):
    """Exception raised when the environment does not describe a usable setup.

    Carries the exit code to stop on, since a mistake in the environment is
    reported to whoever started the container rather than retried.
    """

    def __init__(self, return_code: ReturnCodes, message: str) -> None:
        super().__init__(message)
        self.return_code = return_code


@dataclass(frozen=True)
class QBittorrentConfig:
    url: str
    username: str
    password: str


@dataclass(frozen=True)
class Config:
    gluetun_url: str
    gluetun_api_key: str | None
    gluetun_port_wait_duration: int
    retry_interval: int
    success_interval: int
    service: QBittorrentConfig


def _get_required(name: str) -> str:
    """Read an environment variable that has no sensible default."""
    if (value := getenv(name)) is None:
        raise ConfigurationError(
            ReturnCodes.MISSING_ENVIRONMENT_VARIABLE,
            f"Environment variable {name} is required",
        )
    return value


def _get_integer(name: str, default: int) -> int:
    """Read a duration in seconds, which has to be a whole number."""
    if (value := getenv(name)) is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ConfigurationError(
            ReturnCodes.INVALID_ENVIRONMENT_VARIABLE,
            f"Environment variable {name} must be an integer, got {value!r}",
        ) from error


def _get_service_config() -> QBittorrentConfig:
    """Read the configuration of the one service SERVICE_TYPE names."""
    service_type = _get_required("SERVICE_TYPE")
    if service_type != QBITTORRENT_SERVICE_TYPE:
        raise ConfigurationError(
            ReturnCodes.UNKNOWN_SERVICE_TYPE,
            f"Invalid SERVICE_TYPE: {service_type}",
        )
    return QBittorrentConfig(
        url=_get_required("QBITTORRENT_URL"),
        username=_get_required("QBITTORRENT_USERNAME"),
        password=_get_required("QBITTORRENT_PASSWORD"),
    )


def get_configuration() -> Config:
    """Read the whole environment, or raise ConfigurationError."""
    return Config(
        gluetun_url=_get_required("GLUETUN_URL"),
        # Optional: gluetun's control server may be set up unauthenticated.
        gluetun_api_key=getenv("GLUETUN_API_KEY"),
        gluetun_port_wait_duration=_get_integer("GLUETUN_PORT_WAIT_DURATION", 300),
        retry_interval=_get_integer("RETRY_INTERVAL", 10),
        success_interval=_get_integer("SUCCESS_INTERVAL", 60 * 5),
        service=_get_service_config(),
    )
