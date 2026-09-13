# SPDX-License-Identifier: GPL-3.0-or-later
#
# A minimal stand-in for the LCD driver that records draw calls, so the widget
# and renderer layers can be tested without a display or a webserver.

from typing import Any, Dict, List


class FakeLcd:
    def __init__(self, width: int = 480, height: int = 320):
        self.width = width
        self.height = height
        self.calls: List[Dict[str, Any]] = []

    def get_width(self) -> int:
        return self.width

    def get_height(self) -> int:
        return self.height

    def _record(self, name: str, kwargs: Dict[str, Any]) -> None:
        self.calls.append({"method": name, **kwargs})

    def DisplayText(self, **kwargs):
        self._record("DisplayText", kwargs)

    def DisplayProgressBar(self, **kwargs):
        self._record("DisplayProgressBar", kwargs)

    def DisplayRadialProgressBar(self, **kwargs):
        self._record("DisplayRadialProgressBar", kwargs)

    def DisplayLineGraph(self, **kwargs):
        self._record("DisplayLineGraph", kwargs)

    def DisplayBitmap(self, **kwargs):
        self._record("DisplayBitmap", kwargs)

    def DisplayPILImage(self, image, x=0, y=0, **kwargs):
        self._record("DisplayPILImage", {"x": x, "y": y})

    def calls_of(self, method: str) -> List[Dict[str, Any]]:
        return [c for c in self.calls if c["method"] == method]
