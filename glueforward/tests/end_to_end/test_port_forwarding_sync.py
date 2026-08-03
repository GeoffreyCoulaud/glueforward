"""Real end-to-end test.

Starts a real gluetun connected to a real ProtonVPN account (WireGuard, port
forwarding enabled) and a real qBittorrent, runs glueforward built from the
repository's Dockerfile, and asserts purely from the outside, through
gluetun's and qBittorrent's own public APIs, that qBittorrent's listening
port ends up matching the port gluetun obtained from ProtonVPN.
"""

import os
import time

import pytest

if not os.environ.get("WIREGUARD_PRIVATE_KEY"):
    pytest.skip(
        "WIREGUARD_PRIVATE_KEY is not set (directly, or via a local "
        ".env.e2e.local file at the repository root); skipping end-to-end "
        "tests that require a real ProtonVPN connection. See CONTRIBUTING.md.",
        allow_module_level=True,
    )


def _poll_until(predicate, *, timeout: float, interval: float = 2.0):
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
    raise TimeoutError(f"Condition not met within {timeout}s") from last_error


def test_glueforward_syncs_qbittorrent_port_to_gluetun_forwarded_port(
    gluetun_client,
    qbittorrent_client,
    # Requested so it is running: this is the application under test.
    glueforward_container,  # pylint: disable=unused-argument
):
    def get_forwarded_port():
        response = gluetun_client.get("/v1/portforward")
        response.raise_for_status()
        return response.json()["port"] or None

    # Nothing before this waits for the tunnel, so this waits out gluetun's
    # whole startup, retried server negotiation included.
    forwarded_port = _poll_until(get_forwarded_port, timeout=240)

    def get_configured_listen_port():
        response = qbittorrent_client.get("/api/v2/app/preferences")
        response.raise_for_status()
        return response.json()["listen_port"] == forwarded_port

    _poll_until(get_configured_listen_port, timeout=120)
