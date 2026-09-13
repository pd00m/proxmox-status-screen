# SPDX-License-Identifier: GPL-3.0-or-later

from proxmox_status_screen.models import (
    Guest,
    Node,
    Server,
    build_context,
    build_summary,
    human_bytes,
    human_rate,
    human_uptime,
)


def _server() -> Server:
    node1 = Node(
        name="pve1",
        status="online",
        cpu=0.5,
        maxcpu=4,
        mem=4 * 1024 ** 3,
        maxmem=8 * 1024 ** 3,
        disk=100 * 1024 ** 3,
        maxdisk=200 * 1024 ** 3,
        guests=[
            Guest(vmid=100, name="web", type="qemu", node="pve1", status="running", cpu=0.25, mem=1, maxmem=2),
            Guest(vmid=200, name="db", type="lxc", node="pve1", status="stopped"),
        ],
    )
    node2 = Node(
        name="pve2",
        status="online",
        cpu=0.25,
        maxcpu=4,
        mem=2 * 1024 ** 3,
        maxmem=8 * 1024 ** 3,
        disk=50 * 1024 ** 3,
        maxdisk=200 * 1024 ** 3,
        guests=[
            Guest(vmid=110, name="build", type="qemu", node="pve2", status="running", cpu=0.1, mem=1, maxmem=2),
        ],
    )
    return Server(name="pve-main", online=True, nodes=[node1, node2], net_in=4096, net_out=2048)


def test_human_bytes():
    assert human_bytes(0) == "0 B"
    assert human_bytes(1024) == "1.0 KiB"
    assert human_bytes(1024 ** 3) == "1.0 GiB"
    assert human_bytes(None) == ""


def test_human_rate():
    assert human_rate(0) == "0 B/s"
    assert human_rate(1024) == "1.0 KB/s"
    assert human_rate(1024 ** 2) == "1.0 MB/s"
    # Decimal units: cross over to MB/s once the rate reaches 500 KB/s
    assert human_rate(499 * 1000) == "499.0 KB/s"
    assert human_rate(500 * 1000) == "0.5 MB/s"
    assert human_rate(None) == ""


def test_server_disk_and_network():
    server = _server()
    # (100 + 50) / (200 + 200) GiB = 37.5%
    assert server.disk_percent == 37.5
    assert server.disk_used == "150.0 GiB"
    assert server.disk_total == "400.0 GiB"
    assert server.net_in_human == "4.1 KB/s"
    assert server.net_out_human == "2.0 KB/s"


def test_human_uptime():
    assert human_uptime(0) == "-"
    assert human_uptime(3661) == "01:01"
    assert human_uptime(90061) == "1d 01:01"


def test_summary_aggregation():
    summary = build_summary([_server()])
    assert summary.servers_total == 1
    assert summary.servers_online == 1
    assert summary.nodes_total == 2
    assert summary.nodes_online == 2
    assert summary.vms_total == 2
    assert summary.vms_running == 2
    assert summary.cts_total == 1
    assert summary.cts_running == 0
    assert summary.guests_total == 3
    assert summary.guests_running == 2
    # weighted CPU: (0.5*4 + 0.25*4) / 8 = 0.375 -> 37.5%
    assert round(summary.cpu_percent, 1) == 37.5
    assert summary.mem_percent == 37.5


def test_build_context():
    context = build_context([_server()])
    assert context["summary"].vms_running == 2
    assert len(context["servers"]) == 1
    assert len(context["nodes"]) == 2
    assert len(context["guests"]) == 3
    assert context["server"]["pve-main"].name == "pve-main"
    assert context["node"]["pve1"].name == "pve1"
