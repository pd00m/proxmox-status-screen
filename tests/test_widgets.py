# SPDX-License-Identifier: GPL-3.0-or-later

from math import ceil
from pathlib import Path

import pytest
from PIL import Image

from fake_lcd import FakeLcd
from proxmox_status_screen import widgets
from proxmox_status_screen.config import load_config
from proxmox_status_screen.models import Guest, Node, Server, Summary

CONFIG_PATH = Path(__file__).resolve().parent / "fixtures" / "dev-config.yaml"


@pytest.fixture(scope="module")
def config():
    return load_config(CONFIG_PATH)


def _guests():
    return [
        Guest(vmid=100, name="web", type="qemu", node="pve1", status="running", cpu=0.5, maxmem=100, mem=50),
        Guest(vmid=200, name="db", type="lxc", node="pve1", status="stopped"),
        Guest(vmid=110, name="build", type="qemu", node="pve2", status="running", cpu=0.1),
    ]


def test_draw_text_resolves_binding(config):
    lcd = FakeLcd()
    ctx = {"summary": Summary(vms_running=3, vms_total=5)}
    widgets.draw_text(lcd, config, {"type": "text", "x": 10, "y": 10, "value": "VM {summary.vms_running}"}, ctx)

    calls = lcd.calls_of("DisplayText")
    assert len(calls) == 1
    assert calls[0]["text"] == "VM 3"
    assert calls[0]["font"].endswith("RobotoMono-Regular.ttf")


def test_empty_binding_draws_space_to_clear(config):
    lcd = FakeLcd()
    widgets.draw_text(lcd, config, {"type": "text", "x": 0, "y": 0, "value": "{missing.value}"}, {})
    assert lcd.calls_of("DisplayText")[0]["text"] == " "


def test_draw_progress_clamps_value(config):
    lcd = FakeLcd()
    ctx = {"summary": Summary(mem_used=50, mem_total=100)}
    widgets.draw_progress(
        lcd,
        config,
        {"type": "progress", "x": 0, "y": 0, "width": 10, "height": 5, "value": "{summary.mem_percent}"},
        ctx,
    )
    assert lcd.calls_of("DisplayProgressBar")[0]["value"] == 50


def test_draw_list_draws_all_rows_and_pages(config):
    lcd = FakeLcd()
    ctx = {"guests": _guests()}
    spec = {
        "type": "list",
        "x": 0,
        "y": 0,
        "rows": 2,
        "row_height": 10,
        "fields": [
            {"x": 0, "value": "{item.name}"},
            {"x": 50, "value": "{item.cpu_percent:.0f}"},
        ],
    }

    assert widgets.list_page_count(spec, ctx) == ceil(3 / 2)

    widgets.draw_list(lcd, config, spec, ctx, page_index=0)
    # rows * fields, including the empty slot on the last page
    assert len(lcd.calls_of("DisplayText")) == 4
    assert lcd.calls_of("DisplayText")[0]["text"] == "web"


def test_list_filters_and_sorts(config):
    ctx = {"guests": _guests()}
    spec = {
        "type": "list",
        "rows": 10,
        "source": "guests",
        "filter_status": ["running"],
        "sort_by": "cpu_percent",
        "sort_reverse": True,
        "fields": [{"x": 0, "value": "{item.name}"}],
    }
    items = widgets.list_items(spec, ctx)
    assert [g.name for g in items] == ["web", "build"]


def test_list_filters_by_server(config):
    s1 = Server(name="pve-main", online=True, nodes=[Node(name="pve1", guests=_guests()[:2])])
    s2 = Server(name="pve-edge", online=True, nodes=[Node(name="edge1", guests=_guests()[2:])])
    ctx = {"servers": [s1, s2], "server": {"pve-main": s1, "pve-edge": s2}}

    assert [g.name for g in widgets.list_items({"server": 1}, ctx)] == ["build"]
    assert [g.name for g in widgets.list_items({"server": "pve-main"}, ctx)] == ["web", "db"]
    assert widgets.list_items({"server": 5}, ctx) == []


def test_draw_histogram_records_image_and_history(config):
    lcd = FakeLcd()
    ctx = {"summary": Summary(cpu_percent=42.0)}
    histories = {}
    spec = {
        "type": "histogram",
        "x": 0,
        "y": 0,
        "width": 100,
        "height": 40,
        "value": "{summary.cpu_percent}",
        "history": 10,
        "min_value": 0,
        "max_value": 100,
        "bar_color": "0, 230, 118",
    }

    widgets.draw_histogram(lcd, config, spec, ctx, histories)
    assert len(lcd.calls_of("DisplayPILImage")) == 1
    assert len(histories["{summary.cpu_percent}"]) == 1

    widgets.draw_histogram(lcd, config, spec, ctx, histories)
    assert len(histories["{summary.cpu_percent}"]) == 2
    assert len(lcd.calls_of("DisplayPILImage")) == 2


def test_histogram_draws_uniform_separated_bars(config):
    class CapturingLcd(FakeLcd):
        def __init__(self):
            super().__init__()
            self.images = []

        def DisplayPILImage(self, image, x=0, y=0, **kwargs):
            self.images.append(image)
            super().DisplayPILImage(image, x, y, **kwargs)

    lcd = CapturingLcd()
    spec = {
        "type": "histogram",
        "x": 0,
        "y": 0,
        "width": 60,
        "height": 20,
        "value": "{summary.cpu_percent}",
        "history": 6,
        "min_value": 0,
        "max_value": 100,
        "bar_color": "0, 230, 118",
        "bar_width": 3,
        "bar_gap": 2,
        "background_color": "0, 0, 0",
    }
    ctx = {"summary": Summary(cpu_percent=100.0)}
    histories = {}
    for _ in range(6):
        widgets.draw_histogram(lcd, config, spec, ctx, histories)

    image = lcd.images[-1].convert("RGB")
    bar = (0, 230, 118)
    runs = []
    current = 0
    for cx in range(60):
        if image.getpixel((cx, 19)) == bar:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)

    assert len(runs) == 6
    assert all(run == 3 for run in runs)


def test_widget_signature_tracks_bound_values(config):
    spec = {"type": "text", "x": 0, "y": 0, "value": "{summary.vms_running}"}

    first = widgets.widget_signature(spec, {"summary": Summary(vms_running=1)})
    same = widgets.widget_signature(spec, {"summary": Summary(vms_running=1)})
    changed = widgets.widget_signature(spec, {"summary": Summary(vms_running=2)})

    assert first == same
    assert first != changed


def test_widget_signature_is_none_for_graphs(config):
    for widget_type in ("line_graph", "histogram"):
        assert widgets.widget_signature({"type": widget_type}, {}) is None


def test_histogram_uses_driver_image_cache(config):
    class CachingLcd(FakeLcd):
        def __init__(self):
            super().__init__()
            self.opened = []

        def open_image(self, path):
            self.opened.append(path)
            return Image.open(path)

    lcd = CachingLcd()
    spec = {
        "type": "histogram",
        "x": 0,
        "y": 0,
        "width": 20,
        "height": 10,
        "value": "{summary.cpu_percent}",
        "history": 5,
    }
    ctx = {"summary": Summary(cpu_percent=10.0)}
    histories = {}

    widgets.draw_histogram(lcd, config, spec, ctx, histories)
    widgets.draw_histogram(lcd, config, spec, ctx, histories)

    assert len(lcd.opened) == 2  # cache hook used, not Image.open directly
