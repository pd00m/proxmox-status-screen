# SPDX-License-Identifier: GPL-3.0-or-later
#
# Minimal Proxmox VE REST API client.
#
# Authentication uses API tokens, which are the appropriate choice for an
# unattended daemon (no ticket/CSRF renewal needed):
#   https://pve.proxmox.com/wiki/Proxmox_VE_API#API_Tokens
#
# Create a token on a Proxmox node with:
#   pveum user token add monitor@pve turing --privsep 0
# then set token_id:  monitor@pve!turing
#           token_secret: <the printed secret>

from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3

from proxmox_status_screen.config import ServerConfig
from proxmox_status_screen.log import logger

# Self-signed certificates are the norm on Proxmox; silence the noisy warning
# when the user explicitly disables verification.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxError(Exception):
    pass


class ProxmoxClient:
    def __init__(self, server: ServerConfig):
        self.server = server
        self.base_url = f"https://{server.host}:{server.port}/api2/json"
        self.session = requests.Session()
        self.session.verify = server.verify_ssl
        self.session.headers.update(
            {
                "Authorization": f"PVEAPIToken={server.token_id}={server.token_secret}",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=self.server.timeout)
        except requests.RequestException as exc:
            raise ProxmoxError(f"Connection error: {exc}") from exc

        if response.status_code == 401:
            raise ProxmoxError("Authentication failed (check token_id/token_secret)")
        if response.status_code >= 400:
            raise ProxmoxError(f"HTTP {response.status_code}: {response.reason}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProxmoxError("Invalid JSON response") from exc

        if "data" not in payload:
            raise ProxmoxError("Malformed API response (no 'data' field)")
        return payload["data"]

    def version(self) -> str:
        data = self._get("/version")
        if isinstance(data, dict):
            return str(data.get("version", ""))
        return ""

    def cluster_resources(self) -> List[Dict[str, Any]]:
        data = self._get("/cluster/resources")
        return data if isinstance(data, list) else []

    def nodes(self) -> List[Dict[str, Any]]:
        data = self._get("/nodes")
        return data if isinstance(data, list) else []

    def node_guests(self, node: str) -> List[Dict[str, Any]]:
        guests: List[Dict[str, Any]] = []
        for kind in ("qemu", "lxc"):
            try:
                data = self._get(f"/nodes/{node}/{kind}")
            except ProxmoxError as exc:
                logger.debug("Could not list %s on node %s: %s", kind, node, exc)
                continue
            if isinstance(data, list):
                guests.extend(data)
        return guests

    def node_rrddata(self, node: str, timeframe: str = "hour", cf: str = "AVERAGE") -> List[Dict[str, Any]]:
        """Return RRD samples for a node (used for network throughput)."""
        data = self._get(
            f"/nodes/{node}/rrddata",
            params={"timeframe": timeframe, "cf": cf},
        )
        return data if isinstance(data, list) else []

    def node_network(self, node: str) -> Tuple[float, float]:
        """Return the node's latest (netin, netout) rate in bytes/s."""
        data = self.node_rrddata(node)
        if not data:
            return 0.0, 0.0
        last = data[-1] or {}
        return float(last.get("netin") or 0.0), float(last.get("netout") or 0.0)

    def close(self) -> None:
        self.session.close()
