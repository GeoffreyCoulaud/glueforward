"""End-to-end tests against a real ProtonVPN tunnel.

These are the only tests that pin glueforward against gluetun's real port
forwarding: a real gluetun connected to a real ProtonVPN account (WireGuard,
port forwarding enabled), a real qBittorrent, and glueforward built from the
repository's Dockerfile. Everything else is asserted from the outside,
through gluetun's and qBittorrent's own public APIs.

A single WireGuard key means a single VPN session, so these tests cannot run
concurrently with one another.
"""

import os

import pytest

from .conftest import poll_until

UNUSED_PORT = 1234

pytestmark = pytest.mark.vpn

if not os.environ.get("WIREGUARD_PRIVATE_KEY"):
    pytest.skip(
        "WIREGUARD_PRIVATE_KEY is not set (directly, or via a local "
        ".env.e2e.local file at the repository root); skipping end-to-end "
        "tests that require a real ProtonVPN connection. See CONTRIBUTING.md.",
        allow_module_level=True,
    )


def test_glueforward_syncs_qbittorrent_port_to_gluetun_forwarded_port(
    gluetun_with_vpn,
    qbittorrent,
    start_glueforward,
):
    forwarded_port = gluetun_with_vpn.wait_for_forwarded_port()
    # A known starting value, so reaching the forwarded port cannot be a fluke.
    qbittorrent.set_preferences(listen_port=UNUSED_PORT)
    assert forwarded_port != UNUSED_PORT

    start_glueforward(gluetun_with_vpn, qbittorrent)

    poll_until(lambda: qbittorrent.get_listen_port() == forwarded_port, timeout=120)


def test_qbittorrent_follows_a_renegotiated_tunnel(
    gluetun_with_vpn,
    qbittorrent,
    start_glueforward,
):
    """A tunnel does not last forever, and each new one forwards its own port."""
    gluetun_with_vpn.wait_for_forwarded_port()
    start_glueforward(gluetun_with_vpn, qbittorrent)
    poll_until(
        lambda: qbittorrent.get_listen_port() == gluetun_with_vpn.get_forwarded_port(),
        timeout=120,
    )

    gluetun_with_vpn.reconnect()
    # ProtonVPN may well hand out the same port again, so this asserts that the
    # port is written afresh rather than that it changed.
    qbittorrent.set_preferences(listen_port=UNUSED_PORT)
    forwarded_port = gluetun_with_vpn.wait_for_forwarded_port()

    poll_until(lambda: qbittorrent.get_listen_port() == forwarded_port, timeout=120)
