# SPDX-License-Identifier: GPL-3.0-or-later

import os
from pathlib import Path

import pytest
import yaml

from proxmox_status_screen.config import ConfigError, load_config

CONFIG_PATH = Path(__file__).resolve().parent / "fixtures" / "dev-config.yaml"


def test_load_dev_config():
    config = load_config(CONFIG_PATH)
    assert config.data.source == "stub"
    assert config.theme == "proxmox-default"
    assert len(config.servers) == 2
    assert config.theme_data.get("widgets")
    assert config.default_background().endswith("background.png")
    assert config.font_path("roboto/Roboto-Regular.ttf").endswith("Roboto-Regular.ttf")


def test_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret-value")
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw["data"]["source"] = "proxmox"
    raw["servers"] = [
        {
            "name": "s1",
            "host": "127.0.0.1",
            "token_id": "monitor@pve!t",
            "token_secret": "${MY_TOKEN}",
        }
    ]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))

    config = load_config(path)
    assert config.servers[0].token_secret == "secret-value"


def test_missing_token_for_proxmox_is_rejected(tmp_path):
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw["data"]["source"] = "proxmox"
    raw["servers"] = [{"name": "s1", "host": "127.0.0.1"}]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ConfigError):
        load_config(path)


def test_no_servers_is_rejected(tmp_path):
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw["servers"] = []
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ConfigError):
        load_config(path)
