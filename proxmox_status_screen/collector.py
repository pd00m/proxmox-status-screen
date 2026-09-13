# SPDX-License-Identifier: GPL-3.0-or-later
#
# Data collection: fetch all configured servers concurrently, turn the raw API
# payloads into the model in models.py, and keep the last known state for servers
# that are temporarily unreachable.

import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List

from proxmox_status_screen.client import ProxmoxClient, ProxmoxError
from proxmox_status_screen.config import AppConfig, ServerConfig
from proxmox_status_screen.log import logger
from proxmox_status_screen.models import Guest, Node, Server

MAX_BACKOFF_SECONDS = 60.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _guest_from_resource(resource: Dict[str, Any]) -> Guest:
    return Guest(
        vmid=_int(resource.get("vmid")),
        name=str(resource.get("name") or resource.get("vmid") or "?"),
        type=str(resource.get("type", "qemu")),
        node=str(resource.get("node", "")),
        status=str(resource.get("status", "unknown")),
        cpu=_float(resource.get("cpu")),
        maxcpu=_int(resource.get("maxcpu")),
        mem=_int(resource.get("mem")),
        maxmem=_int(resource.get("maxmem")),
        disk=_int(resource.get("disk")),
        maxdisk=_int(resource.get("maxdisk")),
        uptime=_int(resource.get("uptime")),
        tags=str(resource.get("tags", "")),
        template=bool(resource.get("template", False)),
    )


def _node_from_resource(resource: Dict[str, Any]) -> Node:
    return Node(
        name=str(resource.get("node") or str(resource.get("id", "")).split("/")[-1]),
        status=str(resource.get("status", "unknown")),
        cpu=_float(resource.get("cpu")),
        maxcpu=_int(resource.get("maxcpu")),
        mem=_int(resource.get("mem")),
        maxmem=_int(resource.get("maxmem")),
        disk=_int(resource.get("disk")),
        maxdisk=_int(resource.get("maxdisk")),
        uptime=_int(resource.get("uptime")),
    )


def parse_cluster_resources(resources: List[Dict[str, Any]], server_cfg: ServerConfig) -> List[Node]:
    """Build nodes+guests from a /cluster/resources response."""
    nodes: Dict[str, Node] = {}
    for resource in resources:
        if resource.get("type") == "node":
            node = _node_from_resource(resource)
            nodes[node.name] = node

    for resource in resources:
        if resource.get("type") not in ("qemu", "lxc"):
            continue
        node_name = str(resource.get("node", ""))
        node = nodes.get(node_name)
        if node is None:
            node = Node(name=node_name or "?")
            nodes[node_name] = node
        node.guests.append(_guest_from_resource(resource))

    return _apply_node_filter(list(nodes.values()), server_cfg)


def _apply_node_filter(nodes: List[Node], server_cfg: ServerConfig) -> List[Node]:
    if not server_cfg.nodes:
        return nodes
    allowed = set(server_cfg.nodes)
    return [n for n in nodes if n.name in allowed]


class Collector:
    def __init__(self, config: AppConfig):
        self.config = config
        self._last_good: Dict[str, List[Node]] = {}
        self._failures: Dict[str, int] = {}
        self._retry_after: Dict[str, float] = {}
        # One persistent HTTP session per server: reusing it keeps the TLS
        # connection alive instead of reconnecting/authenticating every poll.
        self._clients: Dict[str, ProxmoxClient] = {}
        # The PVE version rarely changes: fetch it once per server.
        self._versions: Dict[str, str] = {}

    def _client(self, server_cfg: ServerConfig) -> ProxmoxClient:
        client = self._clients.get(server_cfg.name)
        if client is None:
            client = ProxmoxClient(server_cfg)
            self._clients[server_cfg.name] = client
        return client

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def refresh(self) -> List[Server]:
        if self.config.data.source == "stub":
            return _stub_servers()

        max_workers = max(1, len(self.config.servers))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(self._fetch_server, self.config.servers))

    def _fetch_server(self, server_cfg: ServerConfig) -> Server:
        now_mono = time.monotonic()
        if now_mono < self._retry_after.get(server_cfg.name, 0.0):
            # Still in backoff: return the last known state without hitting the API
            return self._offline_server(server_cfg, "waiting to retry")

        client = self._client(server_cfg)
        try:
            version = self._versions.get(server_cfg.name)
            if version is None:
                version = client.version()
                self._versions[server_cfg.name] = version
            try:
                resources = client.cluster_resources()
                nodes = parse_cluster_resources(resources, server_cfg)
            except ProxmoxError as exc:
                logger.debug(
                    "cluster/resources failed for %s (%s), falling back to per-node queries",
                    server_cfg.name,
                    exc,
                )
                nodes = self._fetch_via_nodes(client, server_cfg)

            self._failures[server_cfg.name] = 0
            self._retry_after[server_cfg.name] = 0.0
            self._last_good[server_cfg.name] = nodes

            net_in, net_out = self._fetch_network(client, nodes)

            logger.debug(
                "Server %s: %d node(s), %d guest(s)",
                server_cfg.name,
                len(nodes),
                sum(len(n.guests) for n in nodes),
            )
            return Server(
                name=server_cfg.name,
                host=server_cfg.host,
                online=True,
                version=version,
                nodes=nodes,
                last_update=datetime.now(),
                net_in=net_in,
                net_out=net_out,
            )
        except Exception as exc:  # noqa: BLE001 - any failure must not stop the loop
            failures = self._failures.get(server_cfg.name, 0) + 1
            self._failures[server_cfg.name] = failures
            backoff = min(MAX_BACKOFF_SECONDS, 2.0 ** min(failures, 6))
            self._retry_after[server_cfg.name] = time.monotonic() + backoff
            # Drop the cached version so it is refreshed once the server is back.
            self._versions.pop(server_cfg.name, None)
            logger.warning(
                "Server %s unreachable (%s), retrying in %.0fs", server_cfg.name, exc, backoff
            )
            return self._offline_server(server_cfg, str(exc))

    def _fetch_network(self, client: ProxmoxClient, nodes: List[Node]) -> tuple:
        """Sum the latest network rate over all nodes of a server."""
        total_in = 0.0
        total_out = 0.0
        for node in nodes:
            try:
                node_in, node_out = client.node_network(node.name)
            except ProxmoxError as exc:
                logger.debug("Network stats unavailable for node %s: %s", node.name, exc)
                continue
            total_in += node_in
            total_out += node_out
        return total_in, total_out

    def _fetch_via_nodes(self, client: ProxmoxClient, server_cfg: ServerConfig) -> List[Node]:
        nodes: List[Node] = []
        for node_resource in client.nodes():
            node = _node_from_resource(node_resource)
            node.guests = [
                _guest_from_resource(g) for g in client.node_guests(node.name)
            ]
            nodes.append(node)
        return _apply_node_filter(nodes, server_cfg)

    def _offline_server(self, server_cfg: ServerConfig, error: str) -> Server:
        return Server(
            name=server_cfg.name,
            host=server_cfg.host,
            online=False,
            error=error,
            nodes=self._last_good.get(server_cfg.name, []),
            last_update=datetime.now(),
        )


# ---------------------------------------------------------------------------
# Stub data source: lets the UI be developed/tested without any Proxmox server
# (data.source: stub in config.yaml).
# ---------------------------------------------------------------------------

_STUB_GUESTS = [
    ("pve1", "qemu", 100, "web-01", "running"),
    ("pve1", "qemu", 101, "db-01", "running"),
    ("pve1", "lxc", 200, "redis", "running"),
    ("pve1", "lxc", 201, "nginx", "running"),
    ("pve1", "qemu", 102, "backup", "stopped"),
    ("pve2", "qemu", 110, "build-01", "running"),
    ("pve2", "lxc", 210, "dns", "running"),
    ("pve2", "lxc", 211, "monitoring", "running"),
    ("pve2", "qemu", 111, "win-test", "paused"),
    ("edge1", "lxc", 300, "proxy", "running"),
    ("edge1", "lxc", 301, "vpn", "running"),
    ("edge1", "qemu", 130, "mail", "running"),
]


def _stub_value(phase: float, base: float, amplitude: float, t: float) -> float:
    return base + amplitude * (0.5 + 0.5 * math.sin(t / 7.0 + phase))


def _stub_servers() -> List[Server]:
    t = time.time()
    nodes: Dict[str, Node] = {}

    for node_name, kind, vmid, name, status in _STUB_GUESTS:
        node = nodes.get(node_name)
        if node is None:
            node = Node(
                name=node_name,
                status="online",
                cpu=0.0,
                maxcpu=8,
                mem=0,
                maxmem=16 * 1024 ** 3,
                disk=0,
                maxdisk=512 * 1024 ** 3,
                uptime=86400 * (1 + len(nodes)),
            )
            nodes[node_name] = node

        running = status == "running"
        phase = vmid % 17
        cpu = _stub_value(phase, 0.15, 0.6, t) if running else 0.0
        maxmem = (2 if kind == "lxc" else 4) * 1024 ** 3
        mem = int(maxmem * _stub_value(phase + 3, 0.2, 0.6, t)) if running else 0
        guest = Guest(
            vmid=vmid,
            name=name,
            type=kind,
            node=node_name,
            status=status,
            cpu=cpu,
            maxcpu=2 if kind == "lxc" else 4,
            mem=mem,
            maxmem=maxmem,
            disk=int(8 * 1024 ** 3),
            maxdisk=32 * 1024 ** 3,
            uptime=int(3600 * (vmid % 72)) if running else 0,
            tags="stub",
        )
        node.guests.append(guest)
        node.cpu = min(1.0, node.cpu + cpu)
        node.mem += mem

    pve_main = Server(
        name="pve-main",
        host="192.168.1.10",
        online=True,
        version="8.2.2",
        nodes=[nodes["pve1"], nodes["pve2"]],
        last_update=datetime.now(),
        net_in=_stub_value(0, 250_000, 800_000, t),
        net_out=_stub_value(5, 120_000, 400_000, t),
    )
    pve_edge = Server(
        name="pve-edge",
        host="192.168.1.20",
        online=True,
        version="8.1.4",
        nodes=[nodes["edge1"]],
        last_update=datetime.now(),
        net_in=_stub_value(2, 90_000, 300_000, t),
        net_out=_stub_value(9, 40_000, 150_000, t),
    )
    return [pve_main, pve_edge]
