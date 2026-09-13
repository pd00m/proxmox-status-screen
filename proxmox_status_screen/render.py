# SPDX-License-Identifier: GPL-3.0-or-later
#
# Theme renderer: draws static assets once, then refreshes the dynamic widgets.
# Owns the line-graph history buffers and the list page rotation state.

import time
from collections import deque
from typing import Any, Mapping, MutableMapping

from proxmox_status_screen.config import AppConfig
from proxmox_status_screen.display import Display
from proxmox_status_screen.log import logger
from proxmox_status_screen.widgets import draw_widget, list_page_count


class ThemeRenderer:
    def __init__(self, config: AppConfig, display: Display):
        self.config = config
        self.display = display
        self.lcd = display.lcd
        self.histories: MutableMapping[str, deque] = {}

        self.page_index = 0
        self._page_count = 1
        self._page_start = time.monotonic()

    @property
    def widgets(self):
        return self.config.theme_data.get("widgets", []) or []

    def draw_static(self) -> None:
        """Draw theme images/text that never change (called once at startup)."""
        self.display.display_static_images()
        self.display.display_static_text()

    def render(self, context: Mapping[str, Any]) -> None:
        self._update_page(context)
        for spec in self.widgets:
            try:
                draw_widget(
                    self.lcd,
                    self.config,
                    spec,
                    context,
                    self.histories,
                    self.page_index,
                )
            except Exception:  # noqa: BLE001 - a bad widget must not kill the loop
                logger.exception("Error drawing widget type=%s", spec.get("type"))

    def _list_specs(self):
        return [
            spec
            for spec in self.widgets
            if str(spec.get("type", "")).lower() == "list" and spec.get("show") is not False
        ]

    def _page_interval(self) -> float:
        intervals = [float(self.config.render.page_interval)]
        for spec in self._list_specs():
            if spec.get("page_interval") is not None:
                intervals.append(float(spec["page_interval"]))
        return max(0.1, min(intervals))

    def _update_page(self, context: Mapping[str, Any]) -> None:
        page_count = 1
        for spec in self._list_specs():
            page_count = max(page_count, list_page_count(spec, context))

        now = time.monotonic()
        if page_count != self._page_count:
            # Number of pages changed: clamp and restart the timer
            self._page_count = page_count
            self.page_index %= page_count
            self._page_start = now
        elif page_count > 1 and (now - self._page_start) >= self._page_interval():
            self.page_index = (self.page_index + 1) % page_count
            self._page_start = now
