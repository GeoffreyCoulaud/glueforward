"""Unit tests for glueforward.main.config."""

import pytest

from glueforward.main.config import (
    ConfigurationError,
    QBittorrentConfig,
    get_configuration,
)
from glueforward.main.errors import ReturnCodes

from .conftest import GLUETUN_API_KEY, QBITTORRENT_PASSWORD

pytestmark = pytest.mark.usefixtures("valid_environment")


def test_a_valid_environment_describes_the_deployment():
    config = get_configuration()

    assert config.gluetun_url == "http://gluetun"
    assert config.gluetun_api_key == GLUETUN_API_KEY
    assert config.service == QBittorrentConfig(
        url="http://qbittorrent", username="user", password=QBITTORRENT_PASSWORD
    )


def test_the_intervals_have_defaults():
    """A deployment that sets none of them still runs sensibly."""
    config = get_configuration()

    assert config.retry_interval == 10
    assert config.success_interval == 300
    assert config.gluetun_port_wait_duration == 300


@pytest.mark.parametrize(
    "name, attribute",
    [
        ("RETRY_INTERVAL", "retry_interval"),
        ("SUCCESS_INTERVAL", "success_interval"),
        ("GLUETUN_PORT_WAIT_DURATION", "gluetun_port_wait_duration"),
    ],
)
def test_the_intervals_are_read_from_the_environment(monkeypatch, name, attribute):
    monkeypatch.setenv(name, "42")

    assert getattr(get_configuration(), attribute) == 42


def test_a_missing_gluetun_api_key_is_allowed(monkeypatch):
    """gluetun's control server may be set up for unauthenticated access."""
    monkeypatch.delenv("GLUETUN_API_KEY")

    assert get_configuration().gluetun_api_key is None


@pytest.mark.parametrize(
    "name",
    [
        "GLUETUN_URL",
        "SERVICE_TYPE",
        "QBITTORRENT_URL",
        "QBITTORRENT_USERNAME",
        "QBITTORRENT_PASSWORD",
    ],
)
def test_a_missing_required_variable_is_reported(monkeypatch, name):
    monkeypatch.delenv(name)

    with pytest.raises(ConfigurationError) as error:
        get_configuration()

    assert error.value.return_code == ReturnCodes.MISSING_ENVIRONMENT_VARIABLE
    assert name in str(error.value)


@pytest.mark.parametrize(
    "name", ["RETRY_INTERVAL", "SUCCESS_INTERVAL", "GLUETUN_PORT_WAIT_DURATION"]
)
@pytest.mark.parametrize(
    "value",
    ["5m", "10s", "", "2.5", "five"],
    ids=["minutes", "seconds", "empty", "decimal", "word"],
)
def test_a_non_numeric_interval_is_reported(monkeypatch, name, value):
    """Borrowing another tool's duration syntax is the obvious mistake to make."""
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError) as error:
        get_configuration()

    assert error.value.return_code == ReturnCodes.INVALID_ENVIRONMENT_VARIABLE
    assert name in str(error.value)
    assert repr(value) in str(error.value)


def test_an_unknown_service_type_is_reported(monkeypatch):
    monkeypatch.setenv("SERVICE_TYPE", "transmission")

    with pytest.raises(ConfigurationError) as error:
        get_configuration()

    assert error.value.return_code == ReturnCodes.UNKNOWN_SERVICE_TYPE
    assert "transmission" in str(error.value)
