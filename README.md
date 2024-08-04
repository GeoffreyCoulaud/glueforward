# glueforward
A daemon to update the listening port of qbittorrent from gluetun's control server

## Install

TODO install instructions (use docker, from github's container registry)

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
</tbody>
</table>

## Other info

- If the forwarded port hasn't changed, no update is sent to qbittorrent