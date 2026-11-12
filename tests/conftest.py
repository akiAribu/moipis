"""Общие фикстуры тестов."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from app.config_loader import Runtime, build_runtime
from app.journal import MemoryLog

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "purchase_order.yaml"


def load_config_data() -> dict[str, Any]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture
def base_config() -> dict[str, Any]:
    return load_config_data()


@pytest.fixture
def make_runtime() -> Callable[..., Runtime]:
    def _make(
        config: dict[str, Any] | None = None,
        log: MemoryLog | None = None,
    ) -> Runtime:
        data = copy.deepcopy(config if config is not None else load_config_data())
        journal = log if log is not None else MemoryLog()
        return build_runtime(data, journal)

    return _make
