"""Единая точка обработки команд и записи журнала."""

from __future__ import annotations

import json
import shlex
from typing import Any

from .engine import ProcessEngine
from .errors import CommandParseError
from .journal import AuditLog
from .models import CommandResult


class ProcessService:
    """Принимает команду, вызывает исполнитель и пишет ровно одну запись."""

    def __init__(self, engine: ProcessEngine, log: AuditLog) -> None:
        self.engine = engine
        self.log = log

    def handle(self, command: Any, raw: str | None = None) -> CommandResult:
        if not isinstance(command, dict):
            return self._log_error(
                command,
                "invalid_command",
                "Команда должна быть JSON-объектом",
            )

        command_type = command.get("type")
        user = command.get("user")
        object_id = command.get("object")

        if command_type == "start":
            if not _is_nonempty_str(user) or not _is_nonempty_str(object_id):
                return self._log_error(
                    command,
                    "invalid_command",
                    "Для start нужны поля user и object",
                )
            result = self.engine.start(user, object_id)
        elif command_type == "action":
            action = command.get("action")
            if (
                not _is_nonempty_str(user)
                or not _is_nonempty_str(object_id)
                or not _is_nonempty_str(action)
            ):
                return self._log_error(
                    command,
                    "invalid_command",
                    "Для action нужны поля user, object и action",
                )
            result = self.engine.act(user, object_id, action)
        else:
            return self._log_error(
                command,
                "invalid_command",
                f"Неизвестный тип команды: {command_type!r}",
            )

        self._write(command, result, raw)
        return result

    def handle_line(self, line: str, format: str = "auto") -> CommandResult | None:
        """Разбирает строку в текстовом или JSON-формате.

        Пустая строка не является командой и не попадает в журнал.
        """
        if line is None:
            return None
        text = line.strip()
        if not text:
            return None

        if format not in {"auto", "text", "json"}:
            return self._log_error(
                text,
                "invalid_command",
                f"Неизвестный формат ввода: {format!r}",
            )

        use_json = format == "json" or (format == "auto" and text.startswith("{"))
        if use_json:
            try:
                command = json.loads(text)
            except json.JSONDecodeError as exc:
                return self._log_error(
                    text,
                    "invalid_command",
                    f"Некорректный JSON: {exc.msg}",
                )
            return self.handle(command, raw=text)

        try:
            command = parse_text_command(text)
        except CommandParseError as exc:
            return self._log_error(text, "invalid_command", str(exc))
        return self.handle(command, raw=text)

    def _write(
        self,
        command: dict[str, Any],
        result: CommandResult,
        raw: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "command": command,
            "user": command.get("user"),
            "object": command.get("object"),
            "state_before": result.state_before,
            "state_after": result.state_after,
            "result": result.result,
            "reason": result.reason,
        }
        if raw is not None:
            record["raw"] = raw
        if result.reason_code is not None:
            record["reason_code"] = result.reason_code
        self.log.write(record)

    def _log_error(
        self,
        raw: Any,
        code: str,
        reason: str,
    ) -> CommandResult:
        user = raw.get("user") if isinstance(raw, dict) else None
        object_id = raw.get("object") if isinstance(raw, dict) else None
        record = {
            "command": raw,
            "user": user if _is_nonempty_str(user) else None,
            "object": object_id if _is_nonempty_str(object_id) else None,
            "state_before": None,
            "state_after": None,
            "result": "error",
            "reason": reason,
            "reason_code": code,
        }
        self.log.write(record)
        return CommandResult(
            result="error",
            reason=reason,
            reason_code=code,
            state_before=None,
            state_after=None,
        )


def parse_text_command(line: str) -> dict[str, str]:
    """Разбирает удобную текстовую команду.

    start <пользователь> <объект>
    action <пользователь> <объект> <действие>
    """
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise CommandParseError(f"Не удалось разобрать команду: {exc}") from exc

    if not parts:
        raise CommandParseError("Пустая команда")

    command = parts[0].lower()
    if command == "start":
        if len(parts) != 3:
            raise CommandParseError(
                "Формат команды: start <пользователь> <объект>"
            )
        return {"type": "start", "user": parts[1], "object": parts[2]}

    if command == "action":
        if len(parts) != 4:
            raise CommandParseError(
                "Формат команды: action <пользователь> <объект> <действие>"
            )
        return {
            "type": "action",
            "user": parts[1],
            "object": parts[2],
            "action": parts[3],
        }

    raise CommandParseError(
        f"Неизвестная команда {parts[0]!r}. Введите help для справки."
    )


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)
