"""Fixtures for the real, external end-to-end test.

Wires together a real gluetun (connected to a real ProtonVPN account with
port forwarding enabled), a real qBittorrent, and a glueforward image built
from the repository's Dockerfile, on an isolated Docker network. Everything
is asserted from the outside, through the same public APIs a real deployment
would use.

Requires a WIREGUARD_PRIVATE_KEY environment variable (see CONTRIBUTING.md).
It is loaded either from the real environment or from a gitignored
".env.e2e.local" file at the repository root, and is never logged.
"""

import json
import os
import re
import secrets
import subprocess
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import HealthcheckWaitStrategy, LogMessageWaitStrategy

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env.e2e.local")

GLUETUN_CONTROL_PORT = 8000
QBITTORRENT_WEBUI_PORT = 8080
QBITTORRENT_USERNAME = "admin"

# qBittorrent generates a temporary WebUI password on every start where none
# has been persisted yet, and prints it once to stdout.
_TEMPORARY_PASSWORD_PATTERN = re.compile(
    r"temporary password is provided for this session:\s*(\S+)", re.IGNORECASE
)


@pytest.fixture(scope="module")
def network():
    net = Network()
    net.create()
    yield net
    net.remove()


@pytest.fixture(scope="module")
def gluetun_api_key():
    """A throwaway control server API key, generated per test run.

    Not a secret from ProtonVPN: it only guards the isolated test network.
    """
    return secrets.token_hex(16)


@pytest.fixture(scope="module")
def gluetun_container(network, gluetun_api_key):
    container = (
        DockerContainer("qmcgaw/gluetun:latest")
        .with_network(network)
        .with_network_aliases("gluetun")
        .with_exposed_ports(GLUETUN_CONTROL_PORT)
        # ProtonVPN WireGuard needs to create a tun interface and manage routes/firewall rules.
        .with_kwargs(cap_add=["NET_ADMIN"], devices=["/dev/net/tun:/dev/net/tun"])
        .with_env("VPN_SERVICE_PROVIDER", "protonvpn")
        .with_env("VPN_TYPE", "wireguard")
        .with_env("WIREGUARD_PRIVATE_KEY", os.environ["WIREGUARD_PRIVATE_KEY"])
        .with_env("SERVER_COUNTRIES", os.environ.get("SERVER_COUNTRIES", "Netherlands"))
        .with_env("VPN_PORT_FORWARDING", "on")
        .with_env(
            "HTTP_CONTROL_SERVER_AUTH_DEFAULT_ROLE",
            json.dumps({"auth": "apikey", "apikey": gluetun_api_key}),
        )
        # gluetun ships a HEALTHCHECK that only turns healthy once the VPN
        # tunnel is actually up; real WireGuard negotiation can take a while.
        .waiting_for(HealthcheckWaitStrategy().with_startup_timeout(180))
    )
    try:
        container.start()
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def gluetun_client(gluetun_container, gluetun_api_key):
    client = httpx.Client(
        base_url=(
            f"http://{gluetun_container.get_container_host_ip()}:"
            f"{gluetun_container.get_exposed_port(GLUETUN_CONTROL_PORT)}"
        ),
        headers={"X-API-Key": gluetun_api_key},
    )
    yield client
    client.close()


@pytest.fixture(scope="module")
def qbittorrent_container(network):
    container = (
        DockerContainer("linuxserver/qbittorrent:latest")
        .with_network(network)
        .with_network_aliases("qbittorrent")
        .with_exposed_ports(QBITTORRENT_WEBUI_PORT)
        .waiting_for(LogMessageWaitStrategy(_TEMPORARY_PASSWORD_PATTERN).with_startup_timeout(60))
    )
    try:
        container.start()
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def qbittorrent_password(qbittorrent_container):
    stdout, stderr = qbittorrent_container.get_logs()
    match = _TEMPORARY_PASSWORD_PATTERN.search(stdout.decode() + stderr.decode())
    assert match, "qBittorrent did not print its temporary WebUI password to the logs"
    return match.group(1)


@pytest.fixture(scope="module")
def qbittorrent_client(qbittorrent_container, qbittorrent_password):
    host = qbittorrent_container.get_container_host_ip()
    port = qbittorrent_container.get_exposed_port(QBITTORRENT_WEBUI_PORT)
    client = httpx.Client(
        base_url=f"http://{host}:{port}",
        # testcontainers maps the WebUI to a random host port, but qBittorrent
        # validates the Host header's port against its own configured WebUI
        # port (8080) and rejects everything else as 401. Container-to-container
        # traffic (glueforward -> qbittorrent:8080) is unaffected, only this
        # external, host-mapped-port client needs the override.
        headers={"Host": f"localhost:{QBITTORRENT_WEBUI_PORT}"},
    )
    login = client.post(
        "/api/v2/auth/login",
        data={"username": QBITTORRENT_USERNAME, "password": qbittorrent_password},
    )
    login.raise_for_status()
    client.cookies.update(login.cookies)
    yield client
    client.close()


@pytest.fixture(scope="module")
def glueforward_image():
    """Build the glueforward image from the repository's Dockerfile.

    Uses `docker buildx build` directly (not testcontainers' `DockerImage`,
    which builds through docker-py's legacy builder API and cannot share
    BuildKit's cache with the Buildx-based CI build/push steps).
    """
    tag = "glueforward:e2e"
    subprocess.run(
        ["docker", "buildx", "build", "--load", "-t", tag, str(REPO_ROOT)],
        check=True,
    )
    return tag


@pytest.fixture
def glueforward_container(
    network,
    glueforward_image,
    gluetun_container,
    gluetun_api_key,
    qbittorrent_container,
    qbittorrent_password,
):
    container = (
        DockerContainer(glueforward_image)
        .with_network(network)
        .with_env("GLUETUN_URL", f"http://gluetun:{GLUETUN_CONTROL_PORT}")
        .with_env("GLUETUN_API_KEY", gluetun_api_key)
        .with_env("SERVICE_TYPE", "qbittorrent")
        .with_env("QBITTORRENT_URL", f"http://qbittorrent:{QBITTORRENT_WEBUI_PORT}")
        .with_env("QBITTORRENT_USERNAME", QBITTORRENT_USERNAME)
        .with_env("QBITTORRENT_PASSWORD", qbittorrent_password)
        .with_env("RETRY_INTERVAL", "2")
        .with_env("SUCCESS_INTERVAL", "5")
        .with_env("LOG_LEVEL", "DEBUG")
    )
    try:
        container.start()
        yield container
    finally:
        container.stop()
