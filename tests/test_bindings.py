# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass

from proxmox_status_screen.bindings import render_binding, resolve_number, resolve_value


@dataclass
class Summary:
    running_vms: int
    total_vms: int


@dataclass
class Server:
    name: str
    status: str


def test_dotted_attribute_binding():
    ctx = {"summary": Summary(running_vms=3, total_vms=5)}
    assert render_binding("{summary.running_vms}/{summary.total_vms}", ctx) == "3/5"


def test_format_spec_binding():
    ctx = {"summary": Summary(running_vms=3, total_vms=5)}
    assert render_binding("{summary.running_vms:>3}", ctx) == "  3"


def test_list_index_and_dict_key_binding():
    ctx = {
        "servers": [Server("pve-main", "online")],
        "server": {"pve-main": Server("pve-main", "online")},
    }
    assert render_binding("{servers[0].name}", ctx) == "pve-main"
    assert render_binding("{server[pve-main].status}", ctx) == "online"


def test_missing_binding_is_empty_and_does_not_raise():
    assert render_binding("{nope.missing}", {}) == ""
    assert render_binding("{summary.nope}", {"summary": Summary(1, 2)}) == ""


def test_resolve_value_returns_raw_object():
    ctx = {"summary": Summary(running_vms=3, total_vms=5)}
    assert resolve_value("{summary.running_vms}", ctx) == 3


def test_resolve_number_handles_units_and_errors():
    ctx = {"summary": Summary(running_vms=42, total_vms=5)}
    assert resolve_number("{summary.running_vms}", ctx) == 42.0
    assert resolve_number("{summary.missing}", ctx) != resolve_number("{summary.missing}", ctx)  # NaN
    assert resolve_number("not a binding", ctx) != resolve_number("not a binding", ctx)  # NaN
