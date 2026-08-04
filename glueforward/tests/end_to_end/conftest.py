"""Fixtures for the end-to-end tests.

Everything is asserted from the outside, through the same public APIs a real
deployment would use, against glueforward built from the repository's own
Dockerfile.

Every container fixture is function-scoped: each test gets its own network,
its own qBittorrent and its own glueforward. Nothing is shared, so tests
inherit no state from one another, may run in any order, and may run in
parallel.

Tests needing a real VPN tunnel additionally require a WIREGUARD_PRIVATE_KEY
environment variable (see CONTRIBUTING.md). It is loaded either from the real
environment or from a gitignored ".env.e2e.local" file at the repository root,
and is never logged.
"""

# pytest resolves fixtures by parameter name, so the shadowing is deliberate.
# pylint: disable=redefined-outer-name

import base64
import http.server
import json
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest
from dotenv import load_dotenv
from filelock import FileLock
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from ..external_contracts import (
    GLUETUN_API_KEY_HEADER,
    GLUETUN_INVALID_API_KEY_STATUS,
    GLUETUN_NO_FORWARDED_PORT,
    GLUETUN_PORT_FORWARD_PATH,
    GLUETUN_PORT_KEY,
    QBITTORRENT_EXPIRED_SESSION_STATUS,
    QBITTORRENT_LOGIN_PATH,
    QBITTORRENT_PREFERENCES_PATH,
    QBITTORRENT_SET_PREFERENCES_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env.e2e.local")

GLUETUN_CONTROL_PORT = 8000
GLUETUN_ALIAS = "gluetun"
QBITTORRENT_WEBUI_PORT = 8080
QBITTORRENT_ALIAS = "qbittorrent"
QBITTORRENT_USERNAME = "admin"
GLUEFORWARD_IMAGE_TAG = "glueforward:e2e"

# The intervals glueforward is started with here, short enough for a test
# to watch several ticks go by.
GLUEFORWARD_RETRY_INTERVAL = 2
GLUEFORWARD_SUCCESS_INTERVAL = 5

# Docker's alias for the host, so containers can reach servers pytest runs.
HOST_ALIAS = "host.docker.internal"

# qBittorrent generates a temporary WebUI password on every start where none
# has been persisted yet, and prints it once to stdout.
_TEMPORARY_PASSWORD_PATTERN = re.compile(
    r"temporary password is provided for this session:\s*(\S+)", re.IGNORECASE
)


def poll_until(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    interval: float = 0.5,
) -> Any:
    """Call `predicate` until it returns a truthy value, or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
        except Exception as error:  # pylint: disable=broad-exception-caught
            last_error = error
        else:
            if result:
                return result
            last_error = None
        time.sleep(interval)
    raise TimeoutError(
        f"Condition not met within {timeout}s, last error: {last_error!r}"
    ) from last_error


def get_container_logs(container: DockerContainer) -> str:
    """Return everything the container wrote to stdout and stderr so far."""
    stdout, stderr = container.get_logs()
    return (stdout + b"\n" + stderr).decode(errors="replace")


def wait_for_exit_code(container: DockerContainer, *, timeout: float = 60) -> int:
    """Block until the container's process exits, and return its exit code."""
    try:
        return container.get_wrapped_container().wait(timeout=timeout)["StatusCode"]
    except Exception as error:  # pylint: disable=broad-exception-caught
        raise TimeoutError(
            f"glueforward was still running {timeout}s later, logs:\n"
            f"{get_container_logs(container)}"
        ) from error


def get_is_running(container: DockerContainer) -> bool:
    """Whether the container's process is still alive."""
    wrapped = container.get_wrapped_container()
    wrapped.reload()
    return wrapped.status == "running"


def _build_glueforward_image() -> None:
    """Build the image with `docker buildx build`.

    Not testcontainers' `DockerImage`, which builds through docker-py's legacy
    builder API and cannot share BuildKit's cache with the Buildx-based CI
    build/push steps.
    """
    command = ["docker", "buildx", "build", "--load"]
    # The GitHub Actions cache only exists inside a workflow run. Reads are
    # always safe there; writes are opt-in because the cache is shared with
    # the default branch, and untrusted code must never populate it.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        command += ["--cache-from", "type=gha"]
        if os.environ.get("E2E_CACHE_WRITE") == "true":
            command += ["--cache-to", "type=gha,mode=max,ignore-error=true"]
    command += ["-t", GLUEFORWARD_IMAGE_TAG, str(REPO_ROOT)]
    subprocess.run(command, check=True)


@pytest.fixture(scope="session")
def glueforward_image(tmp_path_factory: pytest.TempPathFactory, worker_id: str) -> str:
    """Build the glueforward image from the repository's Dockerfile."""
    if worker_id == "master":
        _build_glueforward_image()
        return GLUEFORWARD_IMAGE_TAG
    # Session fixtures run once per xdist worker, but the image tag is shared.
    marker = tmp_path_factory.getbasetemp().parent / "glueforward-image"
    with FileLock(f"{marker}.lock"):
        if not marker.exists():
            _build_glueforward_image()
            marker.write_text(GLUEFORWARD_IMAGE_TAG)
    return GLUEFORWARD_IMAGE_TAG


def _remove_network(net: Network) -> bool:
    net.remove()
    return True


@pytest.fixture
def network() -> Iterator[Network]:
    net = Network()
    net.create()
    yield net
    # A container's endpoint outlives the container itself by a moment, and the
    # daemon refuses to remove a network still holding one.
    poll_until(lambda: _remove_network(net), timeout=30, interval=1)


@dataclass
class QBittorrent:
    """A running qBittorrent, with a client authenticated for the test's own use."""

    container: DockerContainer
    client: httpx.Client
    password: str

    @property
    def url_for_containers(self) -> str:
        return f"http://{QBITTORRENT_ALIAS}:{QBITTORRENT_WEBUI_PORT}"

    def authenticate(self) -> None:
        response = self.client.post(
            QBITTORRENT_LOGIN_PATH,
            data={"username": QBITTORRENT_USERNAME, "password": self.password},
        )
        response.raise_for_status()
        self.client.cookies.update(response.cookies)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request, reauthenticating once if the test's session expired."""
        response = self.client.request(method, url, **kwargs)
        if response.status_code == QBITTORRENT_EXPIRED_SESSION_STATUS:
            self.authenticate()
            response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def get_preferences(self) -> dict:
        return self._request("GET", QBITTORRENT_PREFERENCES_PATH).json()

    def set_preferences(self, **preferences: Any) -> None:
        self._request(
            "POST",
            QBITTORRENT_SET_PREFERENCES_PATH,
            data={"json": json.dumps(preferences)},
        )

    def get_listen_port(self) -> int:
        return self.get_preferences()["listen_port"]

    def close(self) -> None:
        self.client.close()
        self.container.stop()


def _get_qbittorrent_base_url(container: DockerContainer) -> str:
    return (
        f"http://{container.get_container_host_ip()}:"
        f"{container.get_exposed_port(QBITTORRENT_WEBUI_PORT)}"
    )


def _make_qbittorrent_client(container: DockerContainer) -> httpx.Client:
    return httpx.Client(
        base_url=_get_qbittorrent_base_url(container),
        # testcontainers maps the WebUI to a random host port, but qBittorrent
        # validates the Host header's port against its own configured WebUI
        # port (8080) and rejects everything else. Container-to-container
        # traffic (glueforward -> qbittorrent:8080) is unaffected, only this
        # external, host-mapped-port client needs the override.
        headers={"Host": f"localhost:{QBITTORRENT_WEBUI_PORT}"},
    )


def _start_qbittorrent(network: Network) -> QBittorrent:
    container = (
        DockerContainer("linuxserver/qbittorrent:latest")
        .with_network(network)
        .with_network_aliases(QBITTORRENT_ALIAS)
        .with_exposed_ports(QBITTORRENT_WEBUI_PORT)
        .waiting_for(
            LogMessageWaitStrategy(_TEMPORARY_PASSWORD_PATTERN).with_startup_timeout(120)
        )
    )
    container.start()
    match = _TEMPORARY_PASSWORD_PATTERN.search(get_container_logs(container))
    assert match, "qBittorrent did not print its temporary WebUI password to the logs"
    client = _make_qbittorrent_client(container)
    service = QBittorrent(container=container, client=client, password=match.group(1))
    service.authenticate()
    return service


@pytest.fixture
def qbittorrent(network: Network) -> Iterator[QBittorrent]:
    service = _start_qbittorrent(network)
    yield service
    service.close()


@pytest.fixture
def qbittorrent_stranger(qbittorrent: QBittorrent) -> Iterator[httpx.Client]:
    """A client of the same qBittorrent, with no session of its own.

    For the contract tests that drive authentication themselves, and must be
    free to fail at it without costing the fixture its own session.
    """
    with _make_qbittorrent_client(qbittorrent.container) as client:
        yield client


@pytest.fixture
def gluetun_api_key() -> str:
    """A throwaway control server API key, generated per test.

    Not a secret from ProtonVPN: it only guards the isolated test network.
    """
    return secrets.token_hex(16)


def _write_response(handler: http.server.BaseHTTPRequestHandler, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class FakeGluetun:
    """A stand-in for gluetun's control server, driven by the test.

    Serves only GET /v1/portforward, the single endpoint glueforward calls.
    Lets a test choose the forwarded port, change it mid-run, or fail on
    demand, none of which a real gluetun can be made to do on command. The
    real contract stays pinned by the tests that run against gluetun itself.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.port = 0
        self.status_code = 200
        self.request_count = 0
        self._server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), self._build_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def _build_handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # pylint: disable=invalid-name
                fake.request_count += 1
                if self.headers.get(GLUETUN_API_KEY_HEADER) != fake.api_key:
                    _write_response(
                        self, GLUETUN_INVALID_API_KEY_STATUS, b"Unauthorized\n"
                    )
                elif self.path != GLUETUN_PORT_FORWARD_PATH:
                    _write_response(self, 404, b"Not found\n")
                elif fake.status_code != 200:
                    _write_response(self, fake.status_code, b"Internal Server Error\n")
                else:
                    body = json.dumps(
                        {GLUETUN_PORT_KEY: fake.port, "ports": [fake.port]}
                    ).encode()
                    _write_response(self, 200, body)

            # pylint: disable-next=redefined-builtin
            def log_message(self, format: str, *args: Any) -> None:
                """Silence the handler's default logging to stderr."""

        return Handler

    @property
    def url_for_containers(self) -> str:
        return f"http://{HOST_ALIAS}:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def fake_gluetun(gluetun_api_key: str) -> Iterator[FakeGluetun]:
    fake = FakeGluetun(api_key=gluetun_api_key)
    yield fake
    fake.close()


@dataclass
class Gluetun:
    """A real gluetun container, reached through its control server."""

    container: DockerContainer
    client: httpx.Client
    api_key: str | None

    @property
    def url_for_containers(self) -> str:
        return f"http://{GLUETUN_ALIAS}:{GLUETUN_CONTROL_PORT}"

    def get_forwarded_port(self) -> int:
        response = self.client.get(GLUETUN_PORT_FORWARD_PATH)
        response.raise_for_status()
        return response.json()[GLUETUN_PORT_KEY]

    def wait_for_forwarded_port(self, *, timeout: float = 240) -> int:
        """Wait out the whole tunnel setup, retried server negotiation included."""
        return poll_until(
            lambda: self.get_forwarded_port() or None, timeout=timeout, interval=2
        )

    def _set_status(self, status: str) -> None:
        response = self.client.put("/v1/vpn/status", json={"status": status})
        response.raise_for_status()

    def reconnect(self) -> None:
        """Renegotiate the tunnel, which usually yields a different forwarded port."""
        self._set_status("stopped")
        # Waiting for the port to be dropped, so the caller cannot read the old
        # one back and believe the new tunnel is already up.
        poll_until(
            lambda: self.get_forwarded_port() == GLUETUN_NO_FORWARDED_PORT,
            timeout=60,
            interval=1,
        )
        self._set_status("running")

    def close(self) -> None:
        self.client.close()
        self.container.stop()


def _start_gluetun(
    network: Network,
    api_key: str | None,
    wireguard_private_key: str,
    port_forwarding: bool = True,
) -> Gluetun:
    container = (
        DockerContainer("qmcgaw/gluetun:latest")
        .with_network(network)
        .with_network_aliases(GLUETUN_ALIAS)
        .with_exposed_ports(GLUETUN_CONTROL_PORT)
        .with_kwargs(cap_add=["NET_ADMIN"], devices=["/dev/net/tun:/dev/net/tun"])
        .with_env("VPN_SERVICE_PROVIDER", "protonvpn")
        .with_env("VPN_TYPE", "wireguard")
        .with_env("WIREGUARD_PRIVATE_KEY", wireguard_private_key)
        .with_env("SERVER_COUNTRIES", os.environ.get("SERVER_COUNTRIES", "Netherlands"))
        .with_env("VPN_PORT_FORWARDING", "on" if port_forwarding else "off")
    )
    if port_forwarding:
        container.with_env("PORT_FORWARD_ONLY", "on")
    # Every route is private by default, so an open control server is a setting
    # of its own rather than the absence of one.
    container.with_env(
        "HTTP_CONTROL_SERVER_AUTH_DEFAULT_ROLE",
        json.dumps(
            {"auth": "none"}
            if api_key is None
            else {"auth": "apikey", "apikey": api_key}
        ),
    )
    container.start()
    client = httpx.Client(
        base_url=(
            f"http://{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(GLUETUN_CONTROL_PORT)}"
        ),
        headers={} if api_key is None else {GLUETUN_API_KEY_HEADER: api_key},
    )
    # Docker publishes the port before gluetun listens on it, so waiting on the
    # port alone returns while the control server still resets connections.
    # Any answer will do here: which one it is, is what the contract tests are for.
    poll_until(
        lambda: client.get(GLUETUN_PORT_FORWARD_PATH).status_code > 0, timeout=60
    )
    return Gluetun(container=container, client=client, api_key=api_key)


def _get_meaningless_wireguard_key() -> str:
    """A well-formed key no ProtonVPN session can ever be established with."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture
def gluetun_without_vpn(network: Network, gluetun_api_key: str) -> Iterator[Gluetun]:
    """A real gluetun whose tunnel never comes up, for testing its control server.

    No ProtonVPN session is ever established, so the fixture needs no secret
    and the forwarded port stays at 0 throughout.
    """
    service = _start_gluetun(
        network, gluetun_api_key, _get_meaningless_wireguard_key()
    )
    yield service
    service.close()


@pytest.fixture
def gluetun_without_authentication(network: Network) -> Iterator[Gluetun]:
    """A real gluetun whose control server is set up to ask for nothing.

    GLUETUN_API_KEY is documented as optional for exactly this setup, which
    gluetun calls the "none" authentication method.
    """
    service = _start_gluetun(network, None, _get_meaningless_wireguard_key())
    yield service
    service.close()


@pytest.fixture
def gluetun_without_port_forwarding(
    network: Network, gluetun_api_key: str
) -> Iterator[Gluetun]:
    """A real gluetun asked for no port forwarding at all.

    The misconfiguration GLUETUN_PORT_WAIT_DURATION exists to diagnose, and
    which is only diagnosable if gluetun answers rather than errors.
    """
    service = _start_gluetun(
        network,
        gluetun_api_key,
        _get_meaningless_wireguard_key(),
        port_forwarding=False,
    )
    yield service
    service.close()


@pytest.fixture
def gluetun_with_vpn(
    network: Network,
    gluetun_api_key: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Gluetun]:
    """A real gluetun connected to a real ProtonVPN account.

    One WireGuard key is one VPN session, so two tunnels raised at once would
    fight over it. Holding a lock for the whole test keeps these serialised
    however the suite is run, rather than leaving it to the caller.
    """
    lock_path = tmp_path_factory.getbasetemp().parent / "wireguard-key.lock"
    with FileLock(str(lock_path)):
        service = _start_gluetun(
            network, gluetun_api_key, os.environ["WIREGUARD_PRIVATE_KEY"]
        )
        try:
            yield service
        finally:
            # Only surfaces when the test fails, and is then the only account
            # of why the tunnel never came up.
            print(get_container_logs(service.container))
            service.close()


@pytest.fixture
def start_glueforward(
    network: Network, glueforward_image: str
) -> Iterator[Callable[..., DockerContainer]]:
    """Start glueforward wired to the given services.

    Any environment variable may be overridden by keyword, which is how a test
    hands it a wrong password, a wrong key, or its own intervals.
    """
    started: list[DockerContainer] = []

    def start(
        gluetun: Any = None,
        qbittorrent: QBittorrent | None = None,
        **overrides: Any,
    ) -> DockerContainer:
        environment: dict[str, Any] = {
            "SERVICE_TYPE": "qbittorrent",
            "QBITTORRENT_USERNAME": QBITTORRENT_USERNAME,
            "RETRY_INTERVAL": str(GLUEFORWARD_RETRY_INTERVAL),
            "SUCCESS_INTERVAL": str(GLUEFORWARD_SUCCESS_INTERVAL),
            "LOG_LEVEL": "DEBUG",
        }
        if gluetun is not None:
            environment["GLUETUN_URL"] = gluetun.url_for_containers
            if gluetun.api_key is not None:
                environment["GLUETUN_API_KEY"] = gluetun.api_key
        if qbittorrent is not None:
            environment["QBITTORRENT_URL"] = qbittorrent.url_for_containers
            environment["QBITTORRENT_PASSWORD"] = qbittorrent.password
        container = (
            DockerContainer(glueforward_image)
            .with_network(network)
            .with_kwargs(extra_hosts={HOST_ALIAS: "host-gateway"})
        )
        for name, value in (environment | overrides).items():
            container.with_env(name, str(value))
        container.start()
        started.append(container)
        return container

    yield start
    for container in started:
        container.stop()
