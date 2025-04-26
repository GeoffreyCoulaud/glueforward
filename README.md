# glueslskd

Updates slskd's listening port to be gluetun's forwarded port on the VPN side by modifying slskd.yaml configuration file.

The goal is to no longer query a file for the exposed port status, but instead use gluetun's API. This is in preparation for the [deprecation of the file approach in a future version of gluetun](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md#native-integrations).

## Usage

The recommended way to use glueslskd is with docker compose.

```yml
services:
  glueslskd:
    image: ghcr.io/geoffreycoulaud/glueslskd:latest
    container_name: glueslskd
    environment:
      GLUETUN_URL: "..."
      GLUETUN_API_KEY: "..."
      SLSKD_CONFIG_PATH: "/path/to/slskd.yaml"
    depends_on:
      - gluetun
      - slskd
  gluetun:
    # Insert gluetun service definition here
  slskd:
    # Insert slskd service definition here
```

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
    <td>SLSKD_CONFIG_PATH</td>
    <td>Path to slskd.yaml configuration file</td>
    <td>No</td>
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

1. Optional before gluetun v3.40.0, where all control server routes become private by default

## Other info

- Ensure that gluetun is reachable from glueslskd and that the slskd.yaml file is accessible.  
For example: If you separate services in different networks, make sure glueslskd has access to the appropriate ones.
- [Gluetun wiki - VPN server port forwarding](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)
