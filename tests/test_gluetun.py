"""Unit tests for glueforward.gluetun."""

import httpx
import pytest

from glueforward.gluetun import (
    GluetunAuthFailed,
    GluetunClient,
    GluetunServerError,
    GluetunUnreachable,
)


def test_init_sets_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "secret"
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key="secret")
    assert client.get_forwarded_port() == 1


def test_init_without_api_key_header(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-API-Key" not in request.headers
        return httpx.Response(200, json={"port": 1})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    assert client.get_forwarded_port() == 1


def test_get_forwarded_port_success(mock_httpx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"port": 50000})

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    assert client.get_forwarded_port() == 50000


def test_get_forwarded_port_connect_error(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunUnreachable):
        client.get_forwarded_port()


def test_get_forwarded_port_read_timeout(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunUnreachable):
        client.get_forwarded_port()


def test_get_forwarded_port_unauthorized(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key="bad")
    with pytest.raises(GluetunAuthFailed):
        client.get_forwarded_port()


def test_get_forwarded_port_server_error(mock_httpx):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    mock_httpx(handler)
    client = GluetunClient(url="http://gluetun", api_key=None)
    with pytest.raises(GluetunServerError):
        client.get_forwarded_port()
