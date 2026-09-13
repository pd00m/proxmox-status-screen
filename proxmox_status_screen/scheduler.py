# SPDX-License-Identifier: GPL-3.0-or-later
#
# Runtime scheduling: a worker thread that drains the display update queue, and
# the main monitor loop (collect data -> render frame).

import queue
import threading
import time

from proxmox_status_screen.collector import Collector
from proxmox_status_screen.config import AppConfig
from proxmox_status_screen.log import logger
from proxmox_status_screen.models import build_context
from proxmox_status_screen.render import ThemeRenderer


class UpdateQueueHandler(threading.Thread):
    """Serialize writes to the display in a single worker thread.

    The LCD drivers queue image/text updates when an update_queue is provided;
    this thread executes them one at a time so large bitmap transfers cannot be
    interleaved with other updates.
    """

    def __init__(self, update_queue: "queue.Queue", stop_event: threading.Event):
        super().__init__(name="display-updates", daemon=True)
        self.update_queue = update_queue
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set() or not self.update_queue.empty():
            try:
                func, args = self.update_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                func(*args)
            except Exception:  # noqa: BLE001
                logger.exception("Display update failed")
            finally:
                self.update_queue.task_done()


def run_monitor_loop(
    config: AppConfig,
    collector: Collector,
    renderer: ThemeRenderer,
    stop_event: threading.Event,
) -> None:
    interval = max(0.1, config.render.interval)
    logger.info("Starting monitor loop (interval %.1fs)", interval)

    while not stop_event.is_set():
        started = time.monotonic()
        try:
            servers = collector.refresh()
            context = build_context(servers)
            renderer.render(context)
        except Exception:  # noqa: BLE001 - keep the daemon alive on unexpected errors
            logger.exception("Monitor iteration failed")

        elapsed = time.monotonic() - started
        stop_event.wait(max(0.0, interval - elapsed))

    logger.info("Monitor loop stopped")
