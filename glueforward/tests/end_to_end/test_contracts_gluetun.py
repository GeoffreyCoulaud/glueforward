"""Contract tests for gluetun's control server.

Every branch in GluetunClient keys off something gluetun is assumed to do.
Unit tests can only restate those assumptions; these check them against
gluetun itself, one fact per test, so that a gluetun release changing its
behaviour fails the test naming the fact rather than surfacing somewhere in
the middle of an end-to-end run.

Nothing here goes through glueforward, and no VPN tunnel is needed, so these
run without any secret.
"""

import httpx

from ..external_contracts import (
    GLUETUN_API_KEY_HEADER,
    GLUETUN_INVALID_API_KEY_STATUS,
    GLUETUN_NO_FORWARDED_PORT,
    GLUETUN_PORT_FORWARD_PATH,
    GLUETUN_PORT_KEY,
)

OK = 200


def test_the_port_forward_endpoint_is_served(gluetun_without_vpn):
    """The one endpoint glueforward calls, at the path it calls it on."""
    response = gluetun_without_vpn.client.get(GLUETUN_PORT_FORWARD_PATH)

    assert response.status_code == OK


def test_the_forwarded_port_is_an_integer_under_its_own_key(gluetun_without_vpn):
    """GluetunClient reads this shape out of the body and hands on the number."""
    body = gluetun_without_vpn.client.get(GLUETUN_PORT_FORWARD_PATH).json()

    assert isinstance(body, dict), f"expected an object, got {body!r}"
    assert isinstance(body.get(GLUETUN_PORT_KEY), int), f"got {body!r}"


def test_no_forwarded_port_is_reported_as_zero(gluetun_without_vpn):
    """glueforward waits on this 0, which is worth hearing from gluetun itself.

    A tunnel takes long enough to negotiate that every deployment starts here.
    """
    assert gluetun_without_vpn.get_forwarded_port() == GLUETUN_NO_FORWARDED_PORT


def test_an_invalid_api_key_is_rejected(gluetun_without_vpn):
    """The status glueforward shuts down on, rather than retries."""
    response = gluetun_without_vpn.client.get(
        GLUETUN_PORT_FORWARD_PATH,
        headers={GLUETUN_API_KEY_HEADER: "not-the-api-key"},
    )

    assert response.status_code == GLUETUN_INVALID_API_KEY_STATUS


def test_a_missing_api_key_is_rejected(gluetun_without_vpn):
    """Which is what makes X-API-Key the header carrying it, and not another."""
    url = f"{gluetun_without_vpn.client.base_url}{GLUETUN_PORT_FORWARD_PATH}"

    response = httpx.get(url)

    assert response.status_code == GLUETUN_INVALID_API_KEY_STATUS


def test_an_open_control_server_serves_a_request_without_an_api_key(
    gluetun_without_authentication,
):
    """GLUETUN_API_KEY is documented as optional, which only holds if this does.

    Every route is private by default, so the setup this covers is the one the
    README calls non default, not the absence of any authentication setting.
    """
    response = gluetun_without_authentication.client.get(GLUETUN_PORT_FORWARD_PATH)

    assert response.status_code == OK


def test_port_forwarding_turned_off_is_answered_rather_than_errored(
    gluetun_without_port_forwarding,
):
    """The misconfiguration GLUETUN_PORT_WAIT_DURATION exists to diagnose.

    glueforward tells it from a tunnel still being negotiated by waiting out a
    deadline on this very answer, which it can only do if gluetun gives one.
    """
    response = gluetun_without_port_forwarding.client.get(GLUETUN_PORT_FORWARD_PATH)

    assert response.status_code == OK
    assert response.json()[GLUETUN_PORT_KEY] == GLUETUN_NO_FORWARDED_PORT
