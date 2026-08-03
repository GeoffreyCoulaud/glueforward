"""End-to-end tests for keeping qBittorrent's listening port in sync.

A stand-in stands in for gluetun's control server so the forwarded port can
be chosen and changed on command, which no real gluetun can be made to do.
qBittorrent is real throughout, since its behaviour is what is under test.

No VPN tunnel is needed, so these run without any secret.
"""

from .conftest import get_container_logs, poll_until

FIRST_PORT = 51413
SECOND_PORT = 6881
WRONG_PORT = 1234


def test_a_new_forwarded_port_is_propagated(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """The forwarded port changes whenever the tunnel is renegotiated.

    Syncing once at startup would leave qBittorrent on a dead port for as long
    as the deployment runs, which is the whole reason the loop exists.
    """
    fake_gluetun.port = FIRST_PORT
    start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    fake_gluetun.port = SECOND_PORT

    poll_until(lambda: qbittorrent.get_listen_port() == SECOND_PORT, timeout=60)


def test_a_port_changed_behind_our_back_is_restored(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """Anything may edit the preference: the WebUI, a restore, another tool."""
    fake_gluetun.port = FIRST_PORT
    start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    qbittorrent.set_preferences(listen_port=WRONG_PORT)

    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)


def test_unrelated_preferences_are_left_alone(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """setPreferences takes a partial payload, so the rest must survive it."""
    fake_gluetun.port = FIRST_PORT
    qbittorrent.set_preferences(
        listen_port=WRONG_PORT,
        random_port=True,
        upnp=True,
        max_connec=123,
        dht=False,
    )
    before = qbittorrent.get_preferences()

    start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    after = qbittorrent.get_preferences()
    # A forwarded port is useless if qBittorrent may still pick its own.
    assert after["random_port"] is False
    assert after["upnp"] is False
    assert after["max_connec"] == 123
    assert after["dht"] is False
    changed = {name for name, value in before.items() if after.get(name) != value}
    assert changed == {"listen_port", "random_port", "upnp"}


def test_no_secret_is_written_to_the_logs(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """Logs get pasted into issues, so they must not carry credentials."""
    fake_gluetun.port = FIRST_PORT
    container = start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    logs = get_container_logs(container)
    assert qbittorrent.password not in logs
    assert fake_gluetun.api_key not in logs
