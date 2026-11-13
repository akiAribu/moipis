"""Предикаты, агрегаторы и вычисление значений предметных объектов."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .classes import ClassRegistry
from .errors import ConfigError
from .models import UNSET, DomainObject


class AggregateRegistry:
    """Заменяемый реестр агрегаторов для путей состава."""

    def __init__(self, funcs: dict[str, Callable[[Iterable[Any]], bool]] | None = None):
        self._funcs = dict(funcs) if funcs is not None else {"all": all, "any": any}

    def get(self, name: str | None) -> Callable[[Iterable[Any]], bool]:
        if name is None or name not in self._funcs:
            raise ConfigError(f"Неподдерживаемый агрегатор: {name!r}")
        return self._funcs[name]

    def names(self) -> tuple[str, ...]:
        return tuple(self._funcs)


@dataclass(frozen=True)
class EvalContext:
    """Контекст вычисления предиката."""

    object: DomainObject
    registry: ClassRegistry
    objects: dict[str, DomainObject]
    aggregates: AggregateRegistry


@dataclass(frozen=True)
class Predicate:
    """Именованный предикат из конфигурации."""

    id: str
    op: str
    param: str | None = None
    value: Any = UNSET
    aggregate: str | None = None
    class_id: str | None = None

    def evaluate(self, ctx: EvalContext) -> bool:
        if self.op == "class":
            if self.class_id is None:
                return False
            return ctx.registry.is_subclass(ctx.object.class_id, self.class_id)

        if self.param is None:
            return False

        if "." in self.param:
            head, tail = self.param.split(".", 1)
            param = ctx.registry.param(ctx.object.class_id, head)
            if param is None or param.type != "composition":
                return False

            refs = ctx.object.values.get(head)
            if refs is None:
                refs = []
            if not isinstance(refs, list):
                return False

            if not refs:
                return ctx.aggregates.get(self.aggregate)([])

            results: list[bool] = []
            for ref_id in refs:
                ref_obj = ctx.objects.get(ref_id)
                if ref_obj is None:
                    results.append(False)
                else:
                    results.append(self._eval_scalar(ref_obj, tail, ctx))
            return ctx.aggregates.get(self.aggregate)(results)

        return self._eval_scalar(ctx.object, self.param, ctx)

    def _eval_scalar(
        self,
        obj: DomainObject,
        param_id: str,
        ctx: EvalContext,
    ) -> bool:
        param = ctx.registry.param(obj.class_id, param_id)
        if param is None:
            return False

        value = obj.values.get(param_id)

        if self.op == "filled":
            if param.type == "composition":
                return bool(value)
            return value is not None

        if param.type == "composition":
            if value is None:
                return False
            if not isinstance(value, list):
                return False
            length = len(value)
            if self.op == "in_range":
                return _in_range(length, param.quantity_min, param.quantity_max)
            return _compare(length, self.op, self.value)

        if value is None:
            return False

        if self.op == "in_range":
            if param.type not in {"integer", "decimal"}:
                return False
            return _in_range(value, param.min, param.max)

        return _compare(value, self.op, self.value)


def _compare(left: Any, op: str, right: Any) -> bool:
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    if op not in {"<", "<=", ">", ">="}:
        return False
    if not _is_number(left) or not _is_number(right):
        return False
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    return left >= right


def _in_range(
    value: Any,
    min_value: float | int | None,
    max_value: float | int | None,
) -> bool:
    if not _is_number(value):
        return False
    if min_value is not None and value < min_value:
        return False
    if max_value is not None and value > max_value:
        return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
