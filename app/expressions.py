"""Дерево выражений для условий в ДНФ.

Строки конфигурации не исполняются как код: условие компилируется в
небольшое дерево объектов Expression.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import ConfigError
from .predicates import EvalContext, Predicate


class Expression(Protocol):
    def evaluate(self, ctx: EvalContext) -> bool: ...


@dataclass(frozen=True)
class Always:
    """Условие отсутствует — переход разрешён всегда."""

    def evaluate(self, ctx: EvalContext) -> bool:
        return True


@dataclass(frozen=True)
class And:
    children: tuple[Expression, ...]

    def evaluate(self, ctx: EvalContext) -> bool:
        for child in self.children:
            if not child.evaluate(ctx):
                return False
        return True


@dataclass(frozen=True)
class Or:
    children: tuple[Expression, ...]

    def evaluate(self, ctx: EvalContext) -> bool:
        for child in self.children:
            if child.evaluate(ctx):
                return True
        return False


@dataclass(frozen=True)
class Not:
    child: Expression

    def evaluate(self, ctx: EvalContext) -> bool:
        return not self.child.evaluate(ctx)


@dataclass(frozen=True)
class PredicateExpr:
    predicate: Predicate

    def evaluate(self, ctx: EvalContext) -> bool:
        return self.predicate.evaluate(ctx)


def compile_condition(
    spec: Any,
    predicates: dict[str, Predicate],
) -> Expression:
    """Компилирует ДНФ из конфигурации в дерево выражений.

    Формат: список дизъюнктов, каждый дизъюнкт — список предикатов.
    Перед предикатом может стоять not: строкой "not name" или
    объектом {"not": "name"}.
    """
    if spec is None:
        return Always()
    if not isinstance(spec, list):
        raise ConfigError("Условие перехода должно быть списком дизъюнктов")
    if not spec:
        return Always()

    disjuncts: list[Expression] = []
    for raw_disjunct in spec:
        if not isinstance(raw_disjunct, list):
            raise ConfigError("Дизъюнкт условия должен быть списком предикатов")
        if not raw_disjunct:
            raise ConfigError("Дизъюнкт условия не может быть пустым")

        terms: list[Expression] = []
        for raw_term in raw_disjunct:
            negated = False
            if isinstance(raw_term, str):
                name = raw_term.strip()
                if name.startswith("not "):
                    negated = True
                    name = name[4:].strip()
            elif isinstance(raw_term, dict) and set(raw_term) == {"not"}:
                negated = True
                name = raw_term["not"]
            else:
                raise ConfigError(f"Некорректный предикат в условии: {raw_term!r}")

            if not isinstance(name, str) or not name:
                raise ConfigError(f"Некорректное имя предиката: {raw_term!r}")
            predicate = predicates.get(name)
            if predicate is None:
                raise ConfigError(f"Неизвестный предикат {name!r} в условии")

            expr: Expression = PredicateExpr(predicate)
            terms.append(Not(expr) if negated else expr)

        disjuncts.append(And(tuple(terms)))

    return Or(tuple(disjuncts))
