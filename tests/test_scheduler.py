# SPDX-License-Identifier: GPL-3.0-or-later

import queue
import threading

from proxmox_status_screen.scheduler import UpdateQueueHandler


def test_update_queue_handler_drains_before_stopping():
    update_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    worker = UpdateQueueHandler(update_queue, stop_event)
    worker.start()

    results = []
    for index in range(3):
        update_queue.put((results.append, [index]))
    worker.stop()

    worker.join(timeout=2)
    assert not worker.is_alive()
    assert results == [0, 1, 2]
