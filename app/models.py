"""Модели данных предметной области и исполнения процессов."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class _Unset:
    """Сентинел для отличия отсутствующего значения от явного null."""

    def __repr__(self) -> str:  # pragma: no cover - удобство отладки
        return "<UNSET>"


UNSET = _Unset()


@dataclass(frozen=True)
class ParamDef:
    """Описание параметра класса."""

    id: str
    title: str
    type: str  # string | number | composition
    min: float | int | None = None
    max: float | int | None = None
    default: Any = UNSET
    ref_class: str | None = None
    quantity_min: int | None = None
    quantity_max: int | None = None


@dataclass
class DomainObject:
    """Готовый объект предметной области.

    Значения параметров-составов хранятся как список ID заранее
    загруженных объектов.
    """

    id: str
    class_id: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class User:
    """Пользователь системы."""

    id: str
    name: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateDef:
    """Состояние шаблона процесса."""

    id: str
    title: str
    initial: bool = False
    final: bool = False
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransitionDef:
    """Переход шаблона процесса."""

    from_state: str
    action: str
    to_state: str
    condition: Any  # Expression; Any, чтобы не создавать циклический импорт


@dataclass
class ProcessTemplate:
    """Неизменяемое описание процесса, общее для всех запусков."""

    id: str
    title: str
    class_id: str
    create_roles: tuple[str, ...]
    actions: dict[str, str]
    states: dict[str, StateDef]
    initial_state: str
    transitions: list[TransitionDef]
    by_key: dict[tuple[str, str], list[TransitionDef]] = field(default_factory=dict)


@dataclass
class ProcessInstance:
    """Конкретный запуск процесса над объектом."""

    object_id: str
    template_id: str
    state: str


@dataclass(frozen=True)
class CommandResult:
    """Результат обработки одной команды."""

    result: str  # accepted | rejected | error
    reason: str | None = None
    reason_code: str | None = None
    state_before: str | None = None
    state_after: str | None = None

    @property
    def accepted(self) -> bool:
        return self.result == "accepted"

    @property
    def rejected(self) -> bool:
        return self.result == "rejected"

    @property
    def error(self) -> bool:
        return self.result == "error"
