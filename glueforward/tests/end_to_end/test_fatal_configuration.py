"""End-to-end tests for the mistakes glueforward refuses to keep running on.

What each service answers to a wrong secret is pinned on its own by the
contract tests; what is left here is what glueforward does about it, which
needs a real process in a real container to mean anything.

No VPN tunnel is needed, so these run without any secret.
"""

from glueforward.main.errors import ReturnCodes

from .conftest import get_container_logs, wait_for_exit_code

WRONG_PASSWORD = "definitely-not-the-password"
FORWARDED_PORT = 51413


def test_invalid_qbittorrent_credentials_shut_the_application_down(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """Wrong credentials are a configuration mistake: retrying cannot fix them."""
    fake_gluetun.port = FORWARDED_PORT
    container = start_glueforward(
        fake_gluetun, qbittorrent, QBITTORRENT_PASSWORD=WRONG_PASSWORD
    )

    exit_code = wait_for_exit_code(container, timeout=30)

    assert exit_code == ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    assert "credentials" in get_container_logs(container).lower()


def test_invalid_qbittorrent_credentials_are_tried_only_once(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """qBittorrent bans the caller's IP for an hour after five failed logins.

    Retrying forever locks the user out of their own instance on top of never
    succeeding, and stopping only once banned would reach the same exit code
    by accident, too late.
    """
    fake_gluetun.port = FORWARDED_PORT
    container = start_glueforward(
        fake_gluetun, qbittorrent, QBITTORRENT_PASSWORD=WRONG_PASSWORD
    )
    wait_for_exit_code(container, timeout=30)

    logs = get_container_logs(container)

    assert logs.count("Authenticating to qBittorrent") == 1


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

    exit_code = wait_for_exit_code(container, timeout=30)

    assert exit_code == ReturnCodes.UNRETRYABLE_EXCEPTION_IN_LIFECYCLE
    assert "authenticate to gluetun" in get_container_logs(container).lower()
