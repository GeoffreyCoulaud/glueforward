"""End-to-end tests for how glueforward behaves once something goes wrong.

A stand-in stands in for gluetun's control server so it can be made to fail
on command, which no real gluetun can. qBittorrent is real throughout, since
its behaviour is what is under test.

No VPN tunnel is needed, so these run without any secret.
"""

import time

from .conftest import get_container_logs, get_is_running, poll_until

FIRST_PORT = 51413
SECOND_PORT = 6881

# Generous enough that a container waiting it out is unambiguously stuck.
STOP_TIMEOUT = 20


def test_a_missing_forwarded_port_is_waited_out(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """gluetun reports port 0 until its tunnel has one, which takes a while.

    Starting the whole stack at once is the normal case, so this is where
    every deployment begins rather than an edge case.
    """
    fake_gluetun.port = 0
    container = start_glueforward(fake_gluetun, qbittorrent)
    requests_before = fake_gluetun.request_count
    poll_until(lambda: fake_gluetun.request_count >= requests_before + 3, timeout=60)
    assert get_is_running(container)

    fake_gluetun.port = FIRST_PORT

    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)


def test_sigterm_stops_glueforward_promptly(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """`docker stop` sends SIGTERM, which the kernel drops unless PID 1 handles it.

    Every restart and redeploy then waits out the whole stop timeout before a
    SIGKILL, which is what a4eea28 fixed.
    """
    fake_gluetun.port = FIRST_PORT
    container = start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    wrapped = container.get_wrapped_container()
    started_at = time.monotonic()
    wrapped.stop(timeout=STOP_TIMEOUT)
    elapsed = time.monotonic() - started_at

    assert elapsed < STOP_TIMEOUT / 2, f"took {elapsed:.1f}s to stop"
    # 137 is the SIGKILL the daemon falls back on once its timeout is up.
    assert wrapped.wait()["StatusCode"] == 0
    assert "Received SIGTERM" in get_container_logs(container)


def test_expired_qbittorrent_session_is_renewed(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """A qBittorrent session expires long before a deployment is restarted.

    The default timeout is an hour, so this is a matter of course rather than
    an edge case, and glueforward has to reauthenticate and carry on.
    """
    fake_gluetun.port = FIRST_PORT
    # Far below SUCCESS_INTERVAL, so the session expires between two updates.
    qbittorrent.set_preferences(web_ui_session_timeout=1)
    container = start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    requests_before = fake_gluetun.request_count
    fake_gluetun.port = SECOND_PORT

    poll_until(lambda: qbittorrent.get_listen_port() == SECOND_PORT, timeout=60)
    assert get_is_running(container)
    # An immediate retry that never succeeds would hammer both services with no
    # pause at all, so the update count has to stay in the same order as the ticks.
    assert fake_gluetun.request_count - requests_before < 60


def test_a_gluetun_outage_is_survived(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """gluetun goes away on its own whenever it renegotiates a tunnel."""
    fake_gluetun.port = FIRST_PORT
    container = start_glueforward(fake_gluetun, qbittorrent)
    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=60)

    fake_gluetun.status_code = 503
    requests_before = fake_gluetun.request_count
    poll_until(lambda: fake_gluetun.request_count >= requests_before + 3, timeout=60)
    assert get_is_running(container)

    fake_gluetun.status_code = 200
    fake_gluetun.port = SECOND_PORT

    poll_until(lambda: qbittorrent.get_listen_port() == SECOND_PORT, timeout=60)


def test_qbittorrent_starting_late_is_waited_for(
    fake_gluetun,
    qbittorrent,
    start_glueforward,
):
    """docker compose's depends_on does not wait for a service to be ready.

    Starting the whole stack at once is the normal case, so glueforward has to
    outlive a qBittorrent that is not listening yet.
    """
    fake_gluetun.port = FIRST_PORT
    # The temporary password is regenerated on every start, so pin one first.
    qbittorrent.password = "end-to-end-fixed-password"
    qbittorrent.set_preferences(web_ui_password=qbittorrent.password)
    qbittorrent.stop()

    container = start_glueforward(fake_gluetun, qbittorrent)
    requests_before = fake_gluetun.request_count
    poll_until(lambda: fake_gluetun.request_count >= requests_before + 3, timeout=60)
    assert get_is_running(container)

    qbittorrent.start()

    poll_until(lambda: qbittorrent.get_listen_port() == FIRST_PORT, timeout=90)
    assert get_is_running(container)
