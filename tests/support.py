"""Вспомогательные функции для тестов."""

from __future__ import annotations

from typing import Any

from app.config_loader import Runtime
from app.models import CommandResult


def start(user: str, object_id: str) -> dict[str, str]:
    return {"type": "start", "user": user, "object": object_id}


def act(user: str, object_id: str, action: str) -> dict[str, str]:
    return {
        "type": "action",
        "user": user,
        "object": object_id,
        "action": action,
    }


def run(runtime: Runtime, *commands: dict[str, Any]) -> list[CommandResult]:
    return [runtime.service.handle(command) for command in commands]
