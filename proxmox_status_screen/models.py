# SPDX-License-Identifier: GPL-3.0-or-later
#
# Data model for Proxmox servers, nodes and guests (VMs / containers).
#
# These objects are intentionally plain dataclasses with computed properties:
# the theming engine exposes them directly to format strings such as
# "{summary.running_vms}" or "{guest.cpu_percent:.0f}%".

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def human_bytes(value: Optional[float], suffix: str = "B") -> str:
    """Format a byte count as a compact human-readable string (e.g. 3.4 GiB)."""
    if value is None:
        return ""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    units = ["", "Ki", "Mi", "Gi", "Ti", "Pi"]
    index = 0
    while abs(value) >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{int(value)} {suffix}"
    return f"{value:.1f} {units[index]}{suffix}"


def human_rate(value: Optional[float], suffix: str = "B/s") -> str:
    """Format a byte-per-second rate as a compact human-readable string.

    Uses decimal (1000-based) units and switches to the next unit once the
    value reaches 500, so a rate above 500 KB/s is shown as MB/s.
    """
    if value is None:
        return ""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    units = ["", "K", "M", "G", "T"]
    index = 0
    while abs(value) >= 500 and index < len(units) - 1:
        value /= 1000.0
        index += 1
    if index == 0:
        return f"{int(value)} {suffix}"
    return f"{value:.1f} {units[index]}{suffix}"


def human_uptime(seconds: Optional[int]) -> str:
    """Format an uptime in seconds as e.g. '3d 04:12'."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    if seconds <= 0:
        return "-"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}"
    return f"{hours:02d}:{minutes:02d}"


def _percent(used: Optional[float], total: Optional[float]) -> float:
    if not total:
        return 0.0
    return max(0.0, min(100.0, (used or 0.0) / total * 100.0))


@dataclass
class Guest:
    vmid: int
    name: str
    type: str  # "qemu" (VM) or "lxc" (container)
    node: str
    status: str = "unknown"
    cpu: float = 0.0  # Proxmox reports a 0..1 fraction
    maxcpu: int = 0
    mem: int = 0  # bytes used
    maxmem: int = 0  # bytes total
    disk: int = 0
    maxdisk: int = 0
    uptime: int = 0
    tags: str = ""
    template: bool = False

    @property
    def cpu_percent(self) -> float:
        return max(0.0, min(100.0, self.cpu * 100.0))

    @property
    def mem_percent(self) -> float:
        return _percent(self.mem, self.maxmem)

    @property
    def disk_percent(self) -> float:
        return _percent(self.disk, self.maxdisk)

    @property
    def mem_used(self) -> str:
        return human_bytes(self.mem)

    @property
    def mem_total(self) -> str:
        return human_bytes(self.maxmem)

    @property
    def disk_used(self) -> str:
        return human_bytes(self.disk)

    @property
    def uptime_human(self) -> str:
        return human_uptime(self.uptime)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def status_short(self) -> str:
        """Single-letter status code for the compact guest list."""
        return {
            "running": "R",
            "stopped": "S",
            "paused": "P",
        }.get(self.status, (self.status[:1] or "?").upper())

    @property
    def kind(self) -> str:
        return "VM" if self.type == "qemu" else "CT"


@dataclass
class Node:
    name: str
    status: str = "unknown"
    cpu: float = 0.0
    maxcpu: int = 0
    mem: int = 0
    maxmem: int = 0
    disk: int = 0
    maxdisk: int = 0
    uptime: int = 0
    guests: List[Guest] = field(default_factory=list)

    @property
    def cpu_percent(self) -> float:
        return max(0.0, min(100.0, self.cpu * 100.0))

    @property
    def mem_percent(self) -> float:
        return _percent(self.mem, self.maxmem)

    @property
    def disk_percent(self) -> float:
        return _percent(self.disk, self.maxdisk)

    @property
    def mem_used(self) -> str:
        return human_bytes(self.mem)

    @property
    def mem_total(self) -> str:
        return human_bytes(self.maxmem)

    @property
    def uptime_human(self) -> str:
        return human_uptime(self.uptime)

    @property
    def online(self) -> bool:
        return self.status == "online"

    @property
    def guest_count(self) -> int:
        return len(self.guests)

    @property
    def running_count(self) -> int:
        return sum(1 for g in self.guests if g.is_running)


@dataclass
class Server:
    name: str
    host: str = ""
    online: bool = False
    error: str = ""
    version: str = ""
    nodes: List[Node] = field(default_factory=list)
    last_update: Optional[datetime] = None
    net_in: float = 0.0  # bytes/s, summed over the server's nodes
    net_out: float = 0.0  # bytes/s, summed over the server's nodes

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def guest_count(self) -> int:
        return sum(n.guest_count for n in self.nodes)

    @property
    def running_count(self) -> int:
        return sum(n.running_count for n in self.nodes)

    @property
    def cpu_percent(self) -> float:
        total = sum(n.maxcpu for n in self.nodes)
        if total:
            used = sum(n.cpu * n.maxcpu for n in self.nodes)
            return max(0.0, min(100.0, used / total * 100.0))
        # Fallback when the API does not report maxcpu: average the nodes.
        if not self.nodes:
            return 0.0
        average = sum(n.cpu for n in self.nodes) / len(self.nodes)
        return max(0.0, min(100.0, average * 100.0))

    @property
    def mem_percent(self) -> float:
        used = sum(n.mem for n in self.nodes)
        total = sum(n.maxmem for n in self.nodes)
        return _percent(used, total)

    @property
    def disk_percent(self) -> float:
        used = sum(n.disk for n in self.nodes)
        total = sum(n.maxdisk for n in self.nodes)
        return _percent(used, total)

    @property
    def disk_used(self) -> str:
        return human_bytes(sum(n.disk for n in self.nodes))

    @property
    def disk_total(self) -> str:
        return human_bytes(sum(n.maxdisk for n in self.nodes))

    @property
    def net_in_human(self) -> str:
        return human_rate(self.net_in)

    @property
    def net_out_human(self) -> str:
        return human_rate(self.net_out)

    @property
    def status(self) -> str:
        return "online" if self.online else "offline"


@dataclass
class Summary:
    servers_total: int = 0
    servers_online: int = 0
    nodes_total: int = 0
    nodes_online: int = 0
    vms_total: int = 0
    vms_running: int = 0
    cts_total: int = 0
    cts_running: int = 0
    mem_used: int = 0
    mem_total: int = 0
    disk_used: int = 0
    disk_total: int = 0
    cpu_percent: float = 0.0

    @property
    def guests_total(self) -> int:
        return self.vms_total + self.cts_total

    @property
    def guests_running(self) -> int:
        return self.vms_running + self.cts_running

    @property
    def mem_percent(self) -> float:
        return _percent(self.mem_used, self.mem_total)

    @property
    def disk_percent(self) -> float:
        return _percent(self.disk_used, self.disk_total)

    @property
    def mem_used_human(self) -> str:
        return human_bytes(self.mem_used)

    @property
    def mem_total_human(self) -> str:
        return human_bytes(self.mem_total)

    @property
    def disk_used_human(self) -> str:
        return human_bytes(self.disk_used)

    @property
    def disk_total_human(self) -> str:
        return human_bytes(self.disk_total)


def build_summary(servers: List[Server]) -> Summary:
    summary = Summary()
    summary.servers_total = len(servers)
    summary.servers_online = sum(1 for s in servers if s.online)

    cpu_weight = 0
    cpu_used = 0.0

    for server in servers:
        for node in server.nodes:
            summary.nodes_total += 1
            if node.online:
                summary.nodes_online += 1
            summary.mem_used += node.mem
            summary.mem_total += node.maxmem
            summary.disk_used += node.disk
            summary.disk_total += node.maxdisk
            cpu_weight += node.maxcpu
            cpu_used += node.cpu * node.maxcpu

            for guest in node.guests:
                if guest.type == "qemu":
                    summary.vms_total += 1
                    if guest.is_running:
                        summary.vms_running += 1
                else:
                    summary.cts_total += 1
                    if guest.is_running:
                        summary.cts_running += 1

    if cpu_weight:
        summary.cpu_percent = max(0.0, min(100.0, cpu_used / cpu_weight * 100.0))
    return summary


def build_context(servers: List[Server], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Build the mapping exposed to theme bindings."""
    now = now or datetime.now()

    all_nodes: List[Node] = []
    all_guests: List[Guest] = []
    by_server: Dict[str, Server] = {}
    by_node: Dict[str, Node] = {}

    for server in servers:
        by_server[server.name] = server
        for node in server.nodes:
            all_nodes.append(node)
            by_node[node.name] = node
            all_guests.extend(node.guests)

    return {
        "time": now,
        "date": now,
        "summary": build_summary(servers),
        "servers": servers,
        "server": by_server,
        "nodes": all_nodes,
        "node": by_node,
        "guests": all_guests,
    }
