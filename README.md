# glueforward

Updates application listening ports to match gluetun's forwarded port on the VPN side.

The goal is to no longer query a file for the exposed port status, but instead use gluetun's API. This is in preparation for the [deprecation of the file approach in a future version of gluetun](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md#native-integrations).

## Usage

The recommended way to use glueforward is with docker compose.

<details>
<summary>Using glueforward with qBittorrent</summary>

```yml
services:
  glueforward:
    image: ghcr.io/geoffreycoulaud/glueforward:latest
    container_name: glueforward
    # A non-zero exit is a setup mistake to fix, not something to restart into
    restart: "no"
    environment:
      GLUETUN_URL: "..."
      GLUETUN_API_KEY: "..."
      SERVICE_TYPE: "qbittorrent"
      QBITTORRENT_URL: "..."
      QBITTORRENT_USERNAME: "..."
      QBITTORRENT_PASSWORD: "..."
    depends_on:
      - gluetun
      - qbittorrent
  gluetun:
    # Insert gluetun service definition here
  qbittorrent:
    # Insert qbittorrent service definition here
```

</details>

## Environment variables

<table>
<thead>
  <tr>
    <th>Name</th>
    <th>Description</th>
    <th>Optional</th>
    <th>Default value</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>GLUETUN_URL</td>
    <td>Url to the <a href="https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md#openvpn-and-wireguard">gluetun control server</a></td>
    <td>No</td>
    <td></td>
  </tr>
  <tr>
    <td>GLUETUN_API_KEY</td>
    <td>Your gluetun control server <a href="https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md">API key</a></td>
    <td>No¹</td>
    <td></td>
  </tr>
  <tr>
    <td>GLUETUN_PORT_WAIT_DURATION</td>
    <td>Maximum time to wait in seconds for the first forwarded port</td>
    <td>Yes</td>
    <td>300</td>
  </tr>
  <tr>
    <td>SERVICE_TYPE</td>
    <td>Service to configure</td>
    <td>No</td>
    <td></td>
  </tr>
  <tr>
    <td>QBITTORRENT_URL</td>
    <td>Url to the qbittorrent web UI</td>
    <td>No²</td>
    <td></td>
  </tr>
  <tr>
    <td>QBITTORRENT_USERNAME</td>
    <td>Username to authenticate to qbittorrent</td>
    <td>No²</td>
    <td></td>
  </tr>
  <tr>
    <td>QBITTORRENT_PASSWORD</td>
    <td>Password to authenticate to qbittorrent</td>
    <td>No²</td>
    <td></td>
  </tr>
  <tr>
    <td>SUCCESS_INTERVAL</td>
    <td>Interval in seconds between updates</td>
    <td>Yes</td>
    <td>300</td>
  </tr>
  <tr>
    <td>RETRY_INTERVAL</td>
    <td>Interval in seconds between updates in case of a failure (eg. one of the servers is unreachable)</td>
    <td>Yes</td>
    <td>10</td>
  </tr>
  <tr>
    <td>LOG_LEVEL</td>
    <td>
      Minimum level of severity for a message to be logged.<br/>
      Available values are
      <code>CRITICAL</code>,
      <code>ERROR</code>,
      <code>WARNING</code>,
      <code>INFO</code>,
      <code>DEBUG</code>
    </td>
    <td>Yes</td>
    <td>INFO</td>
  </tr>
</tbody>
</table>

1. Required unless gluetun is setup for unauthenticated access (non default)  
   See the [gluetun control server documentation](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md#authentication-methods) for details.
2. Required when SERVICE_TYPE=qbittorrent, which is the only supported service at the moment.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Stopped on SIGTERM, the signal `docker stop` sends. |
| 1 | A required environment variable is missing. |
| 2 | `SERVICE_TYPE` names a service that is not supported. |
| 3 | An error no retry can fix: credentials gluetun or qBittorrent rejected, a URL that does not point at the expected API, or a first forwarded port that never came. |
| 4 | An environment variable that has to be a whole number holds something else. |

Any code other than 0 is a mistake in the setup.

 [!IMPORTANT]  
> Leave the glueforward container on `restart: "no"` or `restart: on-failure:3`.  
> Glueforward is built to tolerate transitive errors. Restarting-looping would hammer gluetun and the service without fixing the issue. Use `docker logs` to diagnose crashes.  

## Migration : v2 -> v3

Three things changed for an existing deployment.

- **`SERVICE_TYPE` is now required.**  
  It used to be optional, and to default to `qbittorrent`. A container that does not set it now stops on startup with exit code 1.

- **The wait for a first forwarded port is now bounded.**  
  When gluetun still reports no forwarded port `GLUETUN_PORT_WAIT_DURATION` seconds (300 by default) after startup, glueforward stops instead of retrying forever. This surfaces a VPN that is never going to forward a port, typically running without `VPN_PORT_FORWARDING`, or on a provider or server that does not support it. Raise `GLUETUN_PORT_WAIT_DURATION` if your tunnel legitimately takes longer to negotiate its first port. Once a first port has arrived, later disappearances are retried indefinitely, as before.

- **`GLUETUN_API_KEY` is now optional.**  
  Leave it unset when gluetun's control server is set up for unauthenticated access. There is nothing to do if you already set it.

### Coming from v1 with slskd? 

Support for it was removed in v2.0.0, since slskd forwards ports natively as of its v0.24.4. Configure it through [slskd's own VPN integration](https://github.com/slskd/slskd/blob/master/docs/config.md#vpn), and drop the glueforward container.

## Other info

- Ensure that gluetun and your service are reachable from glueforward.
  For example: If you separate services in different networks, make sure glueforward has access to the appropriate ones.
- Service types are mutually exclusive (only one service per container instance). For multiple services, run separate containers with different SERVICE_TYPE values.
- [Gluetun wiki - VPN server port forwarding](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)
