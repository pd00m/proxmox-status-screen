#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
#
# proxmox-status-screen - display Proxmox VE server/node/VM/container status on a
# Turing-compatible USB display.
#
# Usage:
#   python main.py run     # run the daemon (foreground, systemd-friendly)
#   python main.py once    # render a single frame then exit
#   python main.py check   # validate config and test server connectivity

import argparse
import queue
import signal
import sys
import threading
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from proxmox_status_screen.client import ProxmoxClient  # noqa: E402
from proxmox_status_screen.collector import Collector  # noqa: E402
from proxmox_status_screen.config import ConfigError, load_config  # noqa: E402
from proxmox_status_screen.display import Display  # noqa: E402
from proxmox_status_screen.log import logger, setup_logging  # noqa: E402
from proxmox_status_screen.models import build_context  # noqa: E402
from proxmox_status_screen.render import ThemeRenderer  # noqa: E402
from proxmox_status_screen.scheduler import UpdateQueueHandler, run_monitor_loop  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"


def cmd_check(config) -> int:
    """Validate the config and test connectivity to every server."""
    if config.data.source == "stub":
        print("data.source is 'stub': no server connection is performed.")
        return 0

    failures = 0
    for server in config.servers:
        client = ProxmoxClient(server)
        try:
            version = client.version()
            resources = client.cluster_resources()
            nodes = sum(1 for r in resources if r.get("type") == "node")
            guests = sum(1 for r in resources if r.get("type") in ("qemu", "lxc"))
            print(f"OK   {server.name} ({server.host}) PVE {version}: {nodes} node(s), {guests} guest(s)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {server.name} ({server.host}): {exc}")
        finally:
            client.close()

    return 1 if failures else 0


def cmd_once(config) -> int:
    """Render exactly one frame (useful for screenshots/CI)."""
    display = Display(config)
    display.initialize_display()

    renderer = ThemeRenderer(config, display)
    renderer.draw_static()

    collector = Collector(config)
    try:
        context = build_context(collector.refresh())
        renderer.render(context)
    finally:
        collector.close()

    logger.info("Rendered a single frame")
    return 0


def cmd_run(config) -> int:
    """Run the monitor loop until SIGINT/SIGTERM."""
    stop_event = threading.Event()
    update_queue: "queue.Queue" = queue.Queue()

    worker = UpdateQueueHandler(update_queue, stop_event)
    worker.start()

    display = Display(config, update_queue)
    display.initialize_display()

    renderer = ThemeRenderer(config, display)
    renderer.draw_static()

    collector = Collector(config)

    def handle_signal(signum, _frame):
        logger.info("Caught signal %s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        run_monitor_loop(config, collector, renderer, stop_event)
    finally:
        stop_event.set()
        worker.join(timeout=10)
        collector.close()
        display.turn_off()
        logger.info("Stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxmox-status-screen",
        description="Display Proxmox VE status on a Turing-compatible USB display.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to config.yaml (default: %(default)s)",
    )
    parser.add_argument("--log-file", default=None, help="Override log file path")
    parser.add_argument("--log-level", default=None, help="Override console log level")
    parser.add_argument(
        "command",
        choices=["run", "once", "check"],
        help="run: daemon loop | once: render one frame | check: test connectivity",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Bootstrap logging so config load warnings are visible, then reconfigure
    setup_logging(None, "INFO")

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    setup_logging(
        args.log_file or config.log_file,
        args.log_level or config.log_level,
    )

    if args.command == "check":
        return cmd_check(config)
    if args.command == "once":
        return cmd_once(config)
    return cmd_run(config)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
