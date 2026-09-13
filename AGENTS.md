# AGENTS.md

Guide for AI coding agents (and humans) working in **proxmox-status-screen**.

## What this project is

A small CLI daemon that polls one or more Proxmox VE servers over the REST API
and renders nodes, VMs and containers on a Turing-compatible USB display. It is
built on the vendored hardware driver and Pillow drawing primitives of
[turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python)
(see `display_driver/`, GPL-3.0-or-later — keep its upstream copyright headers).

The design separates three concerns:

1. **Data collection** (`proxmox_status_screen/client.py`, `collector.py`) → models.
2. **Rendering** (`proxmox_status_screen/render.py`, `widgets.py`) → pixels.
3. **Hardware driver** (`display_driver/`) → serial/USB/simulated transport.

## Commands

```bash
pip install -r requirements-dev.txt
python main.py once     # render a single frame -> screencap.png (SIMU)
python main.py run      # foreground loop (systemd-friendly)
python main.py check    # validate config + test server connectivity
pytest                  # unit tests
```

All commands accept `--config PATH`, `--log-file PATH`, `--log-level LEVEL`.
`run` and `once` also accept `--interval SECONDS` (`-i`, 5–3600) to override
`render.interval`.

For fast, hardware-free iteration, create a config with `display.revision: SIMU`
and `data.source: stub` (see `tests/fixtures/dev-config.yaml`), then inspect
`screencap.png` or open <http://localhost:5680>.

## Data flow

```
config.yaml ──> proxmox_status_screen/config.py (AppConfig)
                    │
                    ├─ themes/<theme>/theme.yaml  (theme_data)
                    └─ display_driver/...          (hardware)
main.py ─> Collector.refresh() ─> models.build_context() ─> ThemeRenderer.render()
                                                              │
                                                    widgets.draw_widget() ─> lcd.*
```

- `config.yaml` selects hardware (`display.revision`), theme and servers.
- `Collector.refresh()` fetches all servers concurrently, returns `List[Server]`
  and keeps last-known state + backoff for unreachable servers. `stub` data
  source generates demo data.
- `build_context()` turns servers into the mapping exposed to theme bindings.
- `ThemeRenderer` draws static assets once, then re-draws dynamic widgets each
  frame; it owns the graph history buffers and list page rotation. Widgets whose
  resolved inputs are unchanged are skipped (`widgets.widget_signature`), so only
  visible changes are rasterized and sent to the display.
- `UpdateQueueHandler` (in `scheduler.py`) serializes display writes and blocks on
  its queue until work arrives, so an idle daemon uses no periodic CPU.

## Key files

| Path | Responsibility |
|---|---|
| `main.py` | CLI entry point (`run` / `once` / `check`) |
| `proxmox_status_screen/config.py` | Load/validate `config.yaml` + `themes/<t>/theme.yaml`; `AppConfig`; `${ENV}` expansion |
| `proxmox_status_screen/client.py` | Minimal Proxmox REST client (API-token auth) |
| `proxmox_status_screen/collector.py` | Concurrent polling, backoff, stub data source |
| `proxmox_status_screen/models.py` | `Guest` / `Node` / `Server` / `Summary` dataclasses + `build_context()` |
| `proxmox_status_screen/bindings.py` | Resolve `{...}` bindings (`render_binding`, `resolve_value`, `resolve_number`) |
| `proxmox_status_screen/widgets.py` | Pillow widget renderers (`draw_text`, `draw_histogram`, `draw_list`, ...) |
| `proxmox_status_screen/render.py` | `ThemeRenderer`: static draw, per-frame render, page rotation |
| `proxmox_status_screen/display.py` | Display factory (revision → driver) + orientation/size + static assets |
| `proxmox_status_screen/scheduler.py` | Poll/render loop + display write queue |
| `display_driver/` | **Vendored** LCD drivers (do not rewrite; see below) |
| `themes/<name>/theme.yaml` | Theme definition |
| `tests/` | `pytest` tests; `tests/fake_lcd.py` records draw calls |

## Creating a new theme

A theme is a folder under `themes/` containing `theme.yaml` plus its assets
(usually a `background.png`).

```yaml
display:
  size: '8.8"'          # must be one of the sizes in proxmox_status_screen/display.py
  orientation: portrait # portrait | landscape
  rgb_led: 0, 160, 90   # backplate LED color

static_images:
  BACKGROUND:
    path: background.png
    x: 0
    y: 0
    width: 480
    height: 1920

static_text:            # drawn once at startup
  TITLE:
    text: "PROXMOX"
    x: 24
    y: 20
    font: roboto-mono/RobotoMono-Bold.ttf
    font_size: 28
    font_color: 0, 230, 118
    background_image: background.png   # repaint this image under the text

widgets:                # redrawn every frame
  - type: text
    x: 24
    y: 64
    value: "> {servers[0].name}"
    font: roboto-mono/RobotoMono-Bold.ttf
    font_size: 36
    font_color: 0, 230, 118
```

### Display sizes (`display.size`)

`0.96"` 80×160 · `2.1"`/`2.8"` 480×480 · `3.5"` 320×480 · `4.6"` 320×960 ·
`5"` 480×800 · `5.2"` 720×1280 · `8"` 800×1280 · `8.8"`/`9.2"` 480×1920 ·
`12.3"` 720×1920. The size drives the canvas for revision `C` and `SIMU`; other
revisions use their own dimensions.

### Bindings

Values are Python format strings resolved against the context (never raise on a
bad binding — they log and render empty). Available keys:

- `time`, `date` — current `datetime`
- `summary` — aggregates (`vms_running`, `vms_total`, `cts_running`, `mem_percent`, `cpu_percent`, `mem_used_human`, ...)
- `servers` (list) / `server[name]` (dict)
- `nodes` (list) / `node[name]` (dict)
- `guests` (list)
- inside a `list` widget: `item` (aliases `guest` / `node` for the current row)

Examples: `{time:%H:%M:%S}`, `{summary.vms_running}/{summary.vms_total}`,
`{server[pve-main].status}`, `{item.cpu_percent:>3.0f}%`.

Numeric widgets (`histogram`, `line_graph`, `progress`, `radial`) should use a
single-field binding such as `"{servers[0].cpu_percent}"` so `resolve_number()`
can read the raw value instead of a formatted string.

### Widget reference

All widgets accept `show: false` to hide them.

- **`text`** — `value`, `x`, `y`, `width`, `height`, `font`, `font_size`, `font_color`, `background_color`, `background_image`, `align` (`left|center|right`), `anchor` (`lt|mt|rt|lm|mm|rm|lb|mb|rb`).
- **`progress`** — `value`, `x`, `y`, `width`, `height`, `min_value`, `max_value`, `bar_color`, `bar_outline`, `reverse_direction`.
- **`radial`** — `value`, `x`/`y` (center), `radius`, `width` (bar thickness), `min_value`, `max_value`, `angle_start`, `angle_end`, `angle_steps`, `angle_sep`, `clockwise`, `text`, `show_text`, `font`, `font_size`, `font_color`, `bar_color`, `bar_background_color`, `draw_bar_background`, `bar_decoration`, `custom_bbox`, `text_offset`.
- **`line_graph`** — `value`, `x`, `y`, `width`, `height`, `history`, `min_value`, `max_value`, `autoscale`, `line_color`, `line_width`, `axis`, `axis_color`, `axis_font`, `axis_font_size`.
- **`histogram`** — `value`, `x`, `y`, `width`, `height`, `history`, `min_value`, `max_value`, `autoscale`, `bar_color`, `bar_width` (fixed integer bar width, default 3), `bar_gap` (pixels, default 2), `axis`, `axis_color`, `key` (optional history key). Bars are uniform; only the most recent samples that fit are shown.
- **`image`** — `path`, `x`, `y`, `width`, `height`.
- **`list`** — `source` (`guests`/`nodes`/`servers`) **or** `server: <index|name>`
  (gathers that server's guests), `x`, `y`, `width`, `rows`, `row_height`,
  `page_interval`, `sort_by`, `sort_reverse`, `filter_status`, `exclude_templates`,
  and `fields`. Each field is a `text` widget with `x`/`y` **relative to the list**;
  add `color_value` + `color_map` to color a row based on a binding, e.g.:

  ```yaml
  - x: 280
    width: 18
    value: "{item.status_short}"
    font_color: 0, 150, 90
    align: right
    color_value: "{item.status}"
    color_map:
      running: "0, 230, 118"
      stopped: "255, 60, 60"
      paused: "255, 179, 0"
  ```

### Assets, fonts and transparency

- Theme assets are resolved relative to the theme folder (`config.theme_asset`).
- Fonts are resolved relative to `fonts/` (`config.font_path`). Available:
  `roboto-mono/`, `roboto/`.
- If a widget sets `background_image`, that image is painted under it (and
  cropped to the widget box) — this is how stale pixels are erased. Omit
  `background_image`/`background_color` to inherit the theme background.

### Pitfalls that will bite you

- **Histograms repaint their background crop.** If two histograms overlap, the
  one drawn later erases the earlier one's bars. Keep `y + height` of a widget
  `<=` the `y` of the next. This is why the vertical theme's CPU/MEM histograms
  have a gap.
- **Keep baked-in background divider lines in sync** with widget positions. The
  `proxmox-vertical` theme documents its divider y-positions in a comment at the
  top of `theme.yaml`; if you move sections, regenerate `background.png`.
- **Dynamic text must stay at a fixed `x`/`y`.** The driver caches the previous
  bounding box per origin and repaints it to avoid ghosting; moving a widget's
  origin defeats this.
- **Unchanged widgets are skipped.** `ThemeRenderer.render()` compares a
  per-widget signature (`widgets.widget_signature`) and skips drawing when it is
  unchanged. `text`, `progress`, `radial`, `image` and `list` are cacheable;
  `line_graph`, `histogram` and unknown types always redraw. A new widget whose
  output can change without its spec bindings changing must not be treated as
  cacheable.
- **Background images are cached.** Widgets decode their background through
  `lcd.open_image()` (or `widgets._open_background()`), which caches decoded
  images; do not call `Image.open()` directly in a per-frame draw path.
- The `list` widget always iterates `rows` times and draws a space in empty
  slots, so shrinking a list erases removed rows.

## Adding functionality

### A new data field

1. Add the field/property in `proxmox_status_screen/models.py` (`Guest` / `Node` /
   `Server` / `Summary`).
2. It is automatically available as `{item.x}` / `{server.x}` etc. If it is a new
   top-level context key, also expose it in `build_context()`.
3. Add a test in `tests/test_models.py`.

### A new widget type

1. Implement `draw_<type>(lcd, config, spec, context, ...)` in
   `proxmox_status_screen/widgets.py` and dispatch it from `draw_widget()`.
2. Use `config.font_path()` / `config.theme_asset()` and `_background_image()`
   so transparency and theme assets keep working.
3. Document it in `README.md` (Theming → Widgets) and in this file.
4. Add a test in `tests/test_widgets.py` using `tests/fake_lcd.py`.

### A new configuration option

1. Add it to `config.example.yaml` with a comment and a sane default.
2. Add it to the relevant dataclass and `load_config()` in
   `proxmox_status_screen/config.py`.
3. Document it in `README.md` (Configuration).

### A new Proxmox API call

1. Add a method to `ProxmoxClient` in `proxmox_status_screen/client.py` (use `_get`).
2. Populate the model in `proxmox_status_screen/collector.py`.
3. Test with a monkeypatched `_get` (see `tests/test_client.py`).

### A new display revision

Add the driver under `display_driver/lcd/`, register it in the factory in
`proxmox_status_screen/display.py`, then add it to the `config.example.yaml` comment
and the README revision table. Do not route hardware outside that factory.

## Conventions

- **License:** GPL-3.0-or-later. Every `.py` file starts with
  `# SPDX-License-Identifier: GPL-3.0-or-later`.
- **YAML-first:** add user-facing options to `config.example.yaml` and the theme
  schema rather than hardcoding.
- **Minimal diffs:** this is a small, reviewable project. Keep changes focused;
  split unrelated changes into separate PRs.
- **Cross-platform:** Windows, macOS and Linux must keep working. Avoid
  platform-specific hacks unless unavoidable.
- **Never commit secrets:** `config.yaml` is gitignored because it holds API
  tokens. Use `${VAR}` expansion / environment files.
- **Periodic work goes through `scheduler.py`.** Do not add parallel loops that
  write to the display; the `UpdateQueueHandler` serializes writes.
- **Vendored code (`display_driver/`)** comes from turing-smart-screen-python.
  Prefer not to edit it; if you must, preserve the upstream copyright/SPDX
  headers and keep the change minimal.

## Testing

- `pytest` runs everything. `conftest.py` puts the repo root on `sys.path`.
- `tests/fake_lcd.py` is a fake driver that records draw calls — assert on those
  instead of pixels where possible.
- `tests/fixtures/dev-config.yaml` is the canonical SIMU + stub config.
- When you change a widget or model, add/extend a test in the matching
  `tests/test_*.py` file.

## Reference

- `README.md` — user-facing docs, Proxmox setup, configuration and theming.
- `themes/proxmox-default/theme.yaml` — landscape 3.5" example (single server
  panel in the vertical/TUI style).
- `themes/proxmox-vertical/theme.yaml` — portrait 8.8" example (8.8" / revision C).
- `config.example.yaml` — every configuration option, documented.
