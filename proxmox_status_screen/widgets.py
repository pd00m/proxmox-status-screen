# SPDX-License-Identifier: GPL-3.0-or-later
#
# Pillow widget renderer.
#
# Reuses the drawing primitives of the vendored LCD driver (DisplayText,
# DisplayProgressBar, DisplayRadialProgressBar, DisplayLineGraph, DisplayBitmap)
# while adding data bindings and a repeating LIST widget for VMs/containers.

import math
from collections import deque
from math import ceil
from typing import Any, List, Mapping, MutableMapping

from PIL import Image, ImageDraw

from display_driver.lcd.color import parse_color
from proxmox_status_screen.bindings import render_binding, resolve_number
from proxmox_status_screen.config import AppConfig
from proxmox_status_screen.log import logger

DEFAULT_FONT = "roboto-mono/RobotoMono-Regular.ttf"

# Maps a list source name to the singular binding name (so both {item.x} and
# {guest.x} work inside a guests list).
_SINGULAR = {"guests": "guest", "nodes": "node", "servers": "server"}


def _background_image(config: AppConfig, spec: Mapping[str, Any]):
    """Resolve the background for a widget.

    Priority: explicit background_image > explicit background_color (solid) >
    theme background image (transparent over the theme background).
    """
    if "background_image" in spec:
        return config.theme_asset(spec.get("background_image"))
    if "background_color" in spec:
        return None
    return config.default_background()


def draw_widget(
    lcd,
    config: AppConfig,
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
    histories: MutableMapping[str, deque],
    page_index: int = 0,
) -> None:
    widget_type = str(spec.get("type", "")).lower()
    if spec.get("show") is False:
        return

    if widget_type == "text":
        draw_text(lcd, config, spec, context)
    elif widget_type == "progress":
        draw_progress(lcd, config, spec, context)
    elif widget_type == "radial":
        draw_radial(lcd, config, spec, context)
    elif widget_type == "line_graph":
        draw_line_graph(lcd, config, spec, context, histories)
    elif widget_type == "histogram":
        draw_histogram(lcd, config, spec, context, histories)
    elif widget_type == "image":
        draw_image(lcd, config, spec)
    elif widget_type == "list":
        draw_list(lcd, config, spec, context, page_index)
    else:
        logger.warning("Unknown widget type '%s'", widget_type)


def draw_text(lcd, config: AppConfig, spec: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    value = render_binding(spec.get("value"), context)
    # Draw a space to erase a previous value when the binding is empty
    text = str(value) if value != "" else " "

    lcd.DisplayText(
        text=text,
        x=int(spec.get("x", 0)),
        y=int(spec.get("y", 0)),
        width=int(spec.get("width", 0)),
        height=int(spec.get("height", 0)),
        font=config.font_path(spec.get("font", DEFAULT_FONT)),
        font_size=int(spec.get("font_size", 10)),
        font_color=spec.get("font_color", (0, 0, 0)),
        background_color=spec.get("background_color", (255, 255, 255)),
        background_image=_background_image(config, spec),
        align=spec.get("align", "left"),
        anchor=spec.get("anchor", "lt"),
    )


def draw_progress(
    lcd, config: AppConfig, spec: Mapping[str, Any], context: Mapping[str, Any]
) -> None:
    min_value = spec.get("min_value", 0)
    max_value = spec.get("max_value", 100)
    value = resolve_number(spec.get("value"), context, default=min_value)
    if math.isnan(value):
        value = min_value
    value = max(min_value, min(max_value, value))

    lcd.DisplayProgressBar(
        x=int(spec.get("x", 0)),
        y=int(spec.get("y", 0)),
        width=int(spec.get("width", 1)),
        height=int(spec.get("height", 1)),
        min_value=min_value,
        max_value=max_value,
        value=int(value),
        bar_color=spec.get("bar_color", (0, 0, 0)),
        bar_outline=bool(spec.get("bar_outline", False)),
        background_color=spec.get("background_color", (255, 255, 255)),
        background_image=_background_image(config, spec),
        reverse_direction=bool(spec.get("reverse_direction", False)),
    )


def draw_radial(
    lcd, config: AppConfig, spec: Mapping[str, Any], context: Mapping[str, Any]
) -> None:
    min_value = spec.get("min_value", 0)
    max_value = spec.get("max_value", 100)
    value = resolve_number(spec.get("value"), context, default=min_value)
    if math.isnan(value):
        value = min_value
    value = max(min_value, min(max_value, value))

    text = None
    if spec.get("text") is not None:
        text = render_binding(spec.get("text"), context)

    lcd.DisplayRadialProgressBar(
        xc=int(spec.get("x", 0)),
        yc=int(spec.get("y", 0)),
        radius=int(spec.get("radius", 1)),
        bar_width=int(spec.get("width", 1)),
        min_value=min_value,
        max_value=max_value,
        angle_start=spec.get("angle_start", 0),
        angle_end=spec.get("angle_end", 360),
        angle_steps=int(spec.get("angle_steps", 1)),
        angle_sep=int(spec.get("angle_sep", 0)),
        clockwise=bool(spec.get("clockwise", False)),
        value=int(value),
        text=text,
        with_text=bool(spec.get("show_text", True)),
        font=config.font_path(spec.get("font", DEFAULT_FONT)),
        font_size=int(spec.get("font_size", 10)),
        font_color=spec.get("font_color", (0, 0, 0)),
        bar_color=spec.get("bar_color", (0, 0, 0)),
        background_color=spec.get("background_color", (0, 0, 0)),
        background_image=_background_image(config, spec),
        custom_bbox=tuple(spec.get("custom_bbox", (0, 0, 0, 0))),
        text_offset=tuple(spec.get("text_offset", (0, 0))),
        bar_background_color=spec.get("bar_background_color", (0, 0, 0)),
        draw_bar_background=bool(spec.get("draw_bar_background", False)),
        bar_decoration=spec.get("bar_decoration", ""),
    )


def draw_line_graph(
    lcd,
    config: AppConfig,
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
    histories: MutableMapping[str, deque],
) -> None:
    history_size = int(spec.get("history", 30))
    key = str(spec.get("key") or spec.get("value"))
    history = histories.get(key)
    if history is None or history.maxlen != history_size:
        history = deque(history or [], maxlen=history_size)
        histories[key] = history

    value = resolve_number(spec.get("value"), context)
    history.append(value)

    values: List[float] = list(history)
    # Left-pad with NaN so the line does not stretch while the history fills up
    if len(values) < history_size:
        values = [math.nan] * (history_size - len(values)) + values

    line_color = spec.get("line_color", (0, 0, 0))
    lcd.DisplayLineGraph(
        x=int(spec.get("x", 0)),
        y=int(spec.get("y", 0)),
        width=int(spec.get("width", 1)),
        height=int(spec.get("height", 1)),
        values=values,
        min_value=spec.get("min_value", 0),
        max_value=spec.get("max_value", 100),
        autoscale=bool(spec.get("autoscale", False)),
        line_color=line_color,
        line_width=int(spec.get("line_width", 2)),
        graph_axis=bool(spec.get("axis", False)),
        axis_color=spec.get("axis_color", line_color),
        axis_font=config.font_path(spec.get("axis_font", "roboto/Roboto-Black.ttf")),
        axis_font_size=int(spec.get("axis_font_size", 10)),
        background_color=spec.get("background_color", (0, 0, 0)),
        background_image=_background_image(config, spec),
    )


def draw_histogram(
    lcd,
    config: AppConfig,
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
    histories: MutableMapping[str, deque],
) -> None:
    """Draw a vertical-bar histogram of the recent history of a value.

    One bar is drawn per sample (oldest on the left). Missing samples are left
    blank so the chart does not stretch while the history fills up.
    """
    x = int(spec.get("x", 0))
    y = int(spec.get("y", 0))
    width = int(spec.get("width", 1))
    height = int(spec.get("height", 1))
    history_size = int(spec.get("history", 60))

    key = str(spec.get("key") or spec.get("value"))
    history = histories.get(key)
    if history is None or history.maxlen != history_size:
        history = deque(history or [], maxlen=history_size)
        histories[key] = history

    value = resolve_number(spec.get("value"), context)
    history.append(value)

    values: List[float] = list(history)
    if len(values) < history_size:
        values = [math.nan] * (history_size - len(values)) + values

    min_value = float(spec.get("min_value", 0))
    if spec.get("autoscale"):
        finite = [v for v in values if not math.isnan(v)]
        max_value = max(finite) * 1.1 if finite else min_value + 1.0
        if max_value <= min_value:
            max_value = min_value + 1.0
    else:
        max_value = float(spec.get("max_value", 100))
    if max_value <= min_value:
        max_value = min_value + 1.0

    background = _background_image(config, spec)
    if background:
        image = Image.open(background).convert("RGB").crop((x, y, x + width, y + height)).copy()
    else:
        image = Image.new("RGB", (width, height), parse_color(spec.get("background_color", (0, 0, 0))))

    draw = ImageDraw.Draw(image)
    bar_color = parse_color(spec.get("bar_color", (0, 0, 0)))
    gap = float(spec.get("bar_gap", 1))
    bin_width = width / len(values)

    for index, sample in enumerate(values):
        if math.isnan(sample):
            continue
        fraction = (sample - min_value) / (max_value - min_value)
        fraction = max(0.0, min(1.0, fraction))
        bar_height = int(round(fraction * height))
        if bar_height <= 0:
            continue
        left = int(index * bin_width)
        right = int((index + 1) * bin_width - gap)
        if right <= left:
            right = left
        draw.rectangle([left, height - bar_height, right, height - 1], fill=bar_color)

    if spec.get("axis"):
        draw.line([(0, height - 1), (width - 1, height - 1)], fill=parse_color(spec.get("axis_color", bar_color)), width=1)

    lcd.DisplayPILImage(image, x, y)


def draw_image(lcd, config: AppConfig, spec: Mapping[str, Any]) -> None:
    path = config.theme_asset(spec.get("path"))
    if not path:
        logger.warning("Image widget without a 'path'")
        return
    lcd.DisplayBitmap(
        bitmap_path=path,
        x=int(spec.get("x", 0)),
        y=int(spec.get("y", 0)),
        width=int(spec.get("width", 0)),
        height=int(spec.get("height", 0)),
    )


def _sort_key(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return -1
    return str(value)


def list_items(spec: Mapping[str, Any], context: Mapping[str, Any]) -> List[Any]:
    server_ref = spec.get("server")
    if server_ref is not None:
        # Per-server list: gather guests from that server's nodes.
        # `server` may be a server name or a 0-based index into the servers list.
        if isinstance(server_ref, int):
            servers = context.get("servers") or []
            server = servers[server_ref] if 0 <= server_ref < len(servers) else None
        else:
            server = (context.get("server") or {}).get(str(server_ref))
        items = [g for node in getattr(server, "nodes", []) for g in node.guests]
    else:
        source = str(spec.get("source", "guests"))
        items = list(context.get(source, []) or [])

    statuses = spec.get("filter_status")
    if statuses:
        allowed = set(statuses)
        items = [i for i in items if getattr(i, "status", None) in allowed]

    if spec.get("exclude_templates", True):
        items = [i for i in items if not getattr(i, "template", False)]

    sort_by = spec.get("sort_by")
    if sort_by:
        items.sort(key=lambda i: _sort_key(getattr(i, sort_by, None)), reverse=bool(spec.get("sort_reverse", False)))

    return items


def list_page_count(spec: Mapping[str, Any], context: Mapping[str, Any]) -> int:
    rows = max(1, int(spec.get("rows", 1)))
    return max(1, ceil(len(list_items(spec, context)) / rows))


def draw_list(
    lcd,
    config: AppConfig,
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
    page_index: int,
) -> None:
    items = list_items(spec, context)
    rows = max(1, int(spec.get("rows", 1)))
    total_pages = max(1, ceil(len(items) / rows))
    page = page_index % total_pages
    page_items = items[page * rows : page * rows + rows]

    source = str(spec.get("source", "guests"))
    singular = _SINGULAR.get(source, "item")
    row_height = int(spec.get("row_height", 20))
    base_x = int(spec.get("x", 0))
    base_y = int(spec.get("y", 0))
    fields = spec.get("fields", [])

    # Always iterate the full number of rows so rows that disappear are erased.
    for row in range(rows):
        item = page_items[row] if row < len(page_items) else None
        row_context = dict(context)
        row_context["item"] = item
        row_context[singular] = item

        for field in fields:
            field_spec = dict(field)
            field_spec["x"] = base_x + int(field.get("x", 0))
            field_spec["y"] = base_y + row * row_height + int(field.get("y", 0))
            if item is None:
                # Empty slot: draw a space to erase a row that disappeared
                field_spec["value"] = " "
            else:
                color_map = field.get("color_map")
                if color_map:
                    key = render_binding(field.get("color_value", "{item.status}"), row_context)
                    mapped = color_map.get(key)
                    if mapped is not None:
                        field_spec["font_color"] = mapped
            draw_text(lcd, config, field_spec, row_context)
