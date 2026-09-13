# SPDX-License-Identifier: GPL-3.0-or-later
#
# Configuration loading and validation.
#
# Two files drive the application:
#   * config.yaml            - hardware, servers and runtime settings (this file)
#   * themes/<theme>/theme.yaml - what to draw on screen
#
# Any string value in config.yaml may reference an environment variable with the
# ${VAR} syntax. This is the recommended way to provide API token secrets without
# storing them in the file.

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from proxmox_status_screen.log import logger

# Application root (the directory containing main.py and proxmox_status_screen/)
BASE_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = BASE_DIR / "themes"
FONTS_DIR = BASE_DIR / "fonts"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """Raised when config.yaml or a theme file is invalid."""


@dataclass
class DisplayConfig:
    revision: str = "SIMU"
    com_port: str = "AUTO"
    brightness: int = 20
    reverse: bool = False
    reset_on_startup: bool = True
    # Simulated display (revision SIMU) options
    simu_webserver: bool = True
    simu_webserver_port: int = 5678


@dataclass
class RenderConfig:
    interval: float = 5.0
    page_interval: float = 10.0


@dataclass
class DataConfig:
    source: str = "proxmox"  # proxmox | stub


@dataclass
class ServerConfig:
    name: str
    host: str
    port: int = 8006
    token_id: str = ""
    token_secret: str = ""
    verify_ssl: bool = True
    timeout: float = 5.0
    nodes: List[str] = field(default_factory=list)


@dataclass
class AppConfig:
    theme: str
    display: DisplayConfig
    render: RenderConfig
    data: DataConfig
    servers: List[ServerConfig]
    log_file: Optional[str]
    log_level: str
    theme_data: Dict[str, Any]
    theme_path: Path
    base_dir: Path
    fonts_dir: Path

    def theme_asset(self, name: Optional[str]) -> Optional[str]:
        """Resolve a theme-relative asset path to an absolute path."""
        if not name:
            return None
        candidate = Path(name)
        if candidate.is_absolute():
            return str(candidate)
        return str(self.theme_path / candidate)

    def font_path(self, name: str) -> str:
        """Resolve a font name relative to the bundled fonts directory."""
        candidate = Path(name)
        if candidate.is_absolute():
            return str(candidate)
        return str(self.fonts_dir / candidate)

    def default_background(self) -> Optional[str]:
        """Return the theme's background image path, used as transparent widget background."""
        images = self.theme_data.get("static_images") or {}
        for name, image in images.items():
            if str(name).upper() == "BACKGROUND":
                return self.theme_asset(image.get("path"))
        for image in images.values():
            return self.theme_asset(image.get("path"))
        return None


def _expand_env(value: Any, missing: List[str]) -> Any:
    """Recursively replace ${VAR} references with environment values."""
    if isinstance(value, str):
        def replace(match: "re.Match[str]") -> str:
            name = match.group(1)
            if name not in os.environ:
                missing.append(name)
                return ""
            return os.environ[name]

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, dict):
        return {k: _expand_env(v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v, missing) for v in value]
    return value


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rt", encoding="utf8") as stream:
            data = yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise ConfigError(f"File not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"Top-level of {path} must be a mapping")
    return data


def _require(section: Dict[str, Any], key: str, context: str) -> Any:
    if key not in section or section[key] in (None, ""):
        raise ConfigError(f"Missing required key '{key}' in {context}")
    return section[key]


def _build_servers(raw_servers: Any) -> List[ServerConfig]:
    if not raw_servers:
        raise ConfigError("At least one server must be defined under 'servers'")
    if not isinstance(raw_servers, list):
        raise ConfigError("'servers' must be a list")

    servers: List[ServerConfig] = []
    seen_names = set()
    for index, raw in enumerate(raw_servers):
        context = f"servers[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{context} must be a mapping")

        name = _require(raw, "name", context)
        if name in seen_names:
            raise ConfigError(f"Duplicate server name '{name}'")
        seen_names.add(name)

        servers.append(
            ServerConfig(
                name=str(name),
                host=str(_require(raw, "host", context)),
                port=int(raw.get("port", 8006)),
                token_id=str(raw.get("token_id", "")),
                token_secret=str(raw.get("token_secret", "")),
                verify_ssl=bool(raw.get("verify_ssl", True)),
                timeout=float(raw.get("timeout", 5.0)),
                nodes=[str(n) for n in raw.get("nodes", []) or []],
            )
        )
    return servers


def load_config(config_path: Union[str, Path]) -> AppConfig:
    """Load and validate config.yaml, then load the selected theme."""
    config_path = Path(config_path).resolve()
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")

    raw = _load_yaml(config_path)

    missing_env: List[str] = []
    raw = _expand_env(raw, missing_env)
    if missing_env:
        # Not fatal: the value may be unused, but warn so the user notices typos.
        logger.warning(
            "Undefined environment variable(s) referenced in %s: %s",
            config_path,
            ", ".join(sorted(set(missing_env))),
        )

    display_raw = raw.get("display", {}) or {}
    render_raw = raw.get("render", {}) or {}
    data_raw = raw.get("data", {}) or {}

    display = DisplayConfig(
        revision=str(display_raw.get("revision", "SIMU")).upper(),
        com_port=display_raw.get("com_port", "AUTO"),
        brightness=int(display_raw.get("brightness", 20)),
        reverse=bool(display_raw.get("reverse", False)),
        reset_on_startup=bool(display_raw.get("reset_on_startup", True)),
        simu_webserver=bool(display_raw.get("simu_webserver", True)),
        simu_webserver_port=int(display_raw.get("simu_webserver_port", 5678)),
    )

    render = RenderConfig(
        interval=float(render_raw.get("interval", 5.0)),
        page_interval=float(render_raw.get("page_interval", 10.0)),
    )

    data = DataConfig(source=str(data_raw.get("source", "proxmox")).lower())

    theme_name = str(_require(raw, "theme", "config"))
    theme_path = THEMES_DIR / theme_name / "theme.yaml"
    theme_data = _load_yaml(theme_path)
    # Expand env vars in theme too (useful for e.g. text labels)
    theme_data = _expand_env(theme_data, [])

    servers = _build_servers(raw.get("servers"))

    if data.source not in ("proxmox", "stub"):
        raise ConfigError(f"Unknown data.source '{data.source}' (expected 'proxmox' or 'stub')")

    if data.source == "proxmox":
        for server in servers:
            if not server.token_id or not server.token_secret:
                raise ConfigError(
                    f"Server '{server.name}' needs both token_id and token_secret "
                    f"when data.source is 'proxmox'"
                )

    if render.interval <= 0:
        raise ConfigError("render.interval must be > 0")

    config = AppConfig(
        theme=theme_name,
        display=display,
        render=render,
        data=data,
        servers=servers,
        log_file=raw.get("log_file"),
        log_level=str(raw.get("log_level", "INFO")),
        theme_data=theme_data,
        theme_path=theme_path.parent,
        base_dir=BASE_DIR,
        fonts_dir=FONTS_DIR,
    )

    if config.log_file:
        # Make relative log paths relative to the config file location
        log_path = Path(config.log_file)
        if not log_path.is_absolute():
            config.log_file = str(config_path.parent / log_path)

    logger.debug("Loaded configuration from %s (theme=%s)", config_path, theme_name)
    return config
