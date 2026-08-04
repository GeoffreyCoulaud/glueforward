"""The facts glueforward assumes about the services it drives.

Every constant here is a claim about someone else's software. Each one is
pinned against the real service by a contract test in
`end_to_end/test_contracts_*.py`, and scripted by the unit tests that exercise
the branch keying off it.

Sharing them is what makes the link mechanical: when a service changes its
behaviour, the contract test naming that fact fails on its own, instead of the
change surfacing somewhere in the middle of an end-to-end run.
"""

# gluetun's control server.
GLUETUN_PORT_FORWARD_PATH = "/v1/portforward"
GLUETUN_PORT_KEY = "port"
GLUETUN_API_KEY_HEADER = "X-API-Key"
GLUETUN_NO_FORWARDED_PORT = 0
GLUETUN_INVALID_API_KEY_STATUS = 401

# qBittorrent's WebUI API.
QBITTORRENT_LOGIN_PATH = "/api/v2/auth/login"
QBITTORRENT_PREFERENCES_PATH = "/api/v2/app/preferences"
QBITTORRENT_SET_PREFERENCES_PATH = "/api/v2/app/setPreferences"
QBITTORRENT_INVALID_CREDENTIALS_STATUS = 401
QBITTORRENT_BANNED_STATUS = 403
QBITTORRENT_EXPIRED_SESSION_STATUS = 403
