# glueforward

Updates qbittorrent's listening port to be gluetun's forwarded port on the VPN side.

The goal is to no longer query a file for the exposed port status, but instead use gleutun's API. This is in preparation for the [deprecation of the file approach in a future version of gluetun](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md#native-integrations).

## Usage

```yml
services:
	glueforward:
		image: ghcr.io/geoffreycoulaud/glueforward:latest
		container_name: glueforward
		environment:
			GLUETUN_URL: "..."
			QBITTORRENT_URL: "..."
			QBITTORRENT_USERNAME: "..."
			QBITTORRENT_PASSWORD: "qbittorrent_webui_password"
		depends_on:
			- gluetun
			- qbittorrent
	gluetun:
		# Insert gluetun service definition here
	qbittorrent:
		# Insert qbittorrent service definition here
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
		<td>QBITTORRENT_URL</td>
		<td>Url to the qbittorrent web UI</td>
		<td>No</td>
		<td></td>
	</tr>
	<tr>
		<td>QBITTORRENT_USERNAME</td>
		<td>Username to authenticate to qbittorrent</td>
		<td>No</td>
		<td></td>
	</tr>
	<tr>
		<td>QBITTORRENT_PASSWORD</td>
		<td>Password to authenticate to qbittorrent</td>
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

## Other info

- If the forwarded port hasn't changed, no update is sent to qbittorrent
- Ensure that gluetun and qbittorrent are reachable from glueforward.  
For example: If you separate services in different networks, make sure glueforward has access to the appropriate ones.
- [Gluetun wiki - VPN server port forwarding](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)