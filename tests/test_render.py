# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from fake_lcd import FakeLcd
from proxmox_status_screen.config import load_config
from proxmox_status_screen.models import Summary
from proxmox_status_screen.render import ThemeRenderer

CONFIG_PATH = Path(__file__).resolve().parent / "fixtures" / "dev-config.yaml"


class FakeDisplay:
    def __init__(self, lcd):
        self.lcd = lcd

    def display_static_images(self):
        pass

    def display_static_text(self):
        pass


@pytest.fixture()
def config():
    cfg = load_config(CONFIG_PATH)
    cfg.theme_data = {"widgets": []}
    return cfg


def _renderer(config, widgets):
    config.theme_data = {"widgets": widgets}
    lcd = FakeLcd()
    return ThemeRenderer(config, FakeDisplay(lcd)), lcd


def test_render_skips_unchanged_widget(config):
    renderer, lcd = _renderer(
        config,
        [{"type": "text", "x": 0, "y": 0, "value": "{summary.vms_running}"}],
    )

    renderer.render({"summary": Summary(vms_running=1)})
    renderer.render({"summary": Summary(vms_running=1)})
    assert len(lcd.calls_of("DisplayText")) == 1

    renderer.render({"summary": Summary(vms_running=2)})
    assert len(lcd.calls_of("DisplayText")) == 2


def test_render_always_redraws_graphs(config):
    renderer, lcd = _renderer(
        config,
        [{"type": "histogram", "x": 0, "y": 0, "width": 10, "height": 5,
          "value": "{summary.cpu_percent}", "history": 5}],
    )

    context = {"summary": Summary(cpu_percent=10.0)}
    renderer.render(context)
    renderer.render(context)
    assert len(lcd.calls_of("DisplayPILImage")) == 2


def test_render_retries_after_widget_error(config):
    renderer, lcd = _renderer(
        config,
        [{"type": "text", "x": 0, "y": 0, "value": "{summary.vms_running}"}],
    )

    class FlakyLcd(FakeLcd):
        def __init__(self):
            super().__init__()
            self.fail = True

        def DisplayText(self, **kwargs):
            if self.fail:
                self.fail = False
                raise RuntimeError("boom")
            super().DisplayText(**kwargs)

    flaky = FlakyLcd()
    renderer.lcd = flaky
    context = {"summary": Summary(vms_running=1)}
    renderer.render(context)
    renderer.render(context)
    assert len(flaky.calls_of("DisplayText")) == 1
