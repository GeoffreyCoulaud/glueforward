"""End-to-end tests pinning the HTTP contracts glueforward relies on.

Every branch in the clients keys off a status code the real service is
assumed to return. Unit tests can only restate those assumptions; these
tests check them against gluetun and qBittorrent themselves.

No VPN tunnel is needed, so these run without any secret.
"""

from .conftest import get_container_logs, wait_for_exit_code

UNRETRYABLE_EXCEPTION_IN_LIFECYCLE = 3


def test_invalid_qbittorrent_credentials_shut_the_application_down(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """Wrong credentials are a configuration mistake: retrying cannot fix them.

    qBittorrent bans the caller's IP for an hour after five failed logins, so
    retrying forever locks the user out of their own instance on top of never
    succeeding.
    """
    fake_gluetun.port = 51413
    container = start_glueforward(
        fake_gluetun,
        qbittorrent,
        QBITTORRENT_PASSWORD="definitely-not-the-password",
    )

    assert wait_for_exit_code(container, timeout=30) == UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    logs = get_container_logs(container)
    assert "credentials" in logs.lower()
    # Shutting down only once banned would reach the same exit code by accident,
    # after having locked the user out of their own qBittorrent.
    assert logs.count("Authenticating to qBittorrent") == 1


def test_gluetun_reports_port_zero_until_it_forwards_one(gluetun_without_vpn):
    """glueforward waits on this 0, which is worth hearing from gluetun itself.

    A tunnel takes long enough to negotiate that every deployment starts here.
    """
    assert gluetun_without_vpn.get_forwarded_port() == 0


def test_invalid_gluetun_api_key_shuts_the_application_down(
    gluetun_without_vpn,
    start_glueforward,
):
    container = start_glueforward(
        gluetun_without_vpn,
        # No qBittorrent: gluetun is called first, and never gets past its key.
        QBITTORRENT_URL="http://qbittorrent:8080",
        QBITTORRENT_PASSWORD="unused",
        GLUETUN_API_KEY="not-the-api-key",
    )

    assert wait_for_exit_code(container, timeout=30) == UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    assert "authenticate to gluetun" in get_container_logs(container).lower()
