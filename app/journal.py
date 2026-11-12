"""Журнал обработанных команд."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class AuditLog(Protocol):
    """Контракт журнала: одна запись на одну команду."""

    def write(self, record: dict[str, Any]) -> None: ...


class MemoryLog:
    """Журнал в памяти для тестов."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def write(self, record: dict[str, Any]) -> None:
        self.records.append(record)


class JsonLinesLog:
    """Журнал JSONL: один JSON-объект на строку, файл только дописывается."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "JsonLinesLog":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
