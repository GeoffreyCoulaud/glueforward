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

## Other info

- Ensure that gluetun and your service are reachable from glueforward.
  For example: If you separate services in different networks, make sure glueforward has access to the appropriate ones.
- Service types are mutually exclusive (only one service per container instance). For multiple services, run separate containers with different SERVICE_TYPE values.
- [Gluetun wiki - VPN server port forwarding](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)
