# SPDX-License-Identifier: GPL-3.0-or-later

from proxmox_status_screen.client import ProxmoxClient
from proxmox_status_screen.config import ServerConfig


def _client():
    return ProxmoxClient(ServerConfig(name="s1", host="127.0.0.1"))


def test_node_network_reads_last_sample(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: [
            {"netin": 100, "netout": 50},
            {"netin": 4096, "netout": 2048},
        ],
    )
    assert client.node_network("pve1") == (4096.0, 2048.0)
    client.close()


def test_node_network_handles_empty(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_get", lambda path, params=None: [])
    assert client.node_network("pve1") == (0.0, 0.0)
    client.close()
