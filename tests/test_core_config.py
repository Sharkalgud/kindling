"""Tests for core/config.py"""

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.config as config_module
from core.config import (
    _CONFIG_DEFAULTS,
    append_to_queue,
    clear_queue,
    load_config,
    load_queue,
    write_config,
)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path):
    """Redirect CONFIG_PATH and QUEUE_PATH to a temp directory for each test."""
    config_path = tmp_path / "config.json"
    queue_path = tmp_path / "queue.json"
    with (
        patch.object(config_module, "CONFIG_PATH", config_path),
        patch.object(config_module, "QUEUE_PATH", queue_path),
        patch.object(config_module, "DATA_DIR", tmp_path),
    ):
        yield tmp_path


def test_load_config_defaults_when_missing(isolated_paths):
    """load_config() creates config.json with defaults when file is absent."""
    tmp_path = isolated_paths
    cfg = load_config()
    assert cfg == _CONFIG_DEFAULTS
    assert (tmp_path / "config.json").exists()


def test_load_config_reads_existing(isolated_paths):
    """load_config() reads custom values back correctly."""
    tmp_path = isolated_paths
    custom = {"interval_hours": 6, "email_hour": 8}
    (tmp_path / "config.json").write_text(json.dumps(custom))
    cfg = load_config()
    assert cfg["interval_hours"] == 6
    assert cfg["email_hour"] == 8


def test_load_config_merges_missing_keys(isolated_paths):
    """load_config() fills in missing keys from defaults."""
    tmp_path = isolated_paths
    partial = {"interval_hours": 12}
    (tmp_path / "config.json").write_text(json.dumps(partial))
    cfg = load_config()
    assert cfg["interval_hours"] == 12
    assert cfg["email_hour"] == _CONFIG_DEFAULTS["email_hour"]


def test_load_config_recovers_from_bad_json(isolated_paths):
    """load_config() returns defaults and overwrites a corrupt config file."""
    tmp_path = isolated_paths
    (tmp_path / "config.json").write_text("not valid json{{")
    cfg = load_config()
    assert cfg == _CONFIG_DEFAULTS


def test_append_and_load_queue(isolated_paths):
    """append_to_queue + load_queue round-trip preserves records."""
    record1 = {"id": "a", "title": "Page A", "cost": 0.01}
    record2 = {"id": "b", "title": "Page B", "cost": 0.02}
    append_to_queue(record1)
    append_to_queue(record2)
    queue = load_queue()
    assert len(queue) == 2
    assert queue[0]["id"] == "a"
    assert queue[1]["id"] == "b"


def test_clear_queue(isolated_paths):
    """clear_queue() empties the queue to []."""
    append_to_queue({"id": "x", "title": "Something"})
    clear_queue()
    assert load_queue() == []
