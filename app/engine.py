"""Исполнитель процессов: запуск, выбор перехода, обновление состояния."""

from __future__ import annotations

from typing import Iterable

from .classes import ClassRegistry
from .models import (
    CommandResult,
    DomainObject,
    ProcessInstance,
    User,
)
from .predicates import AggregateRegistry, EvalContext
from .templates import TemplateCatalog


class ProcessRepository:
    """Экземпляры процессов в памяти: не более одного на объект."""

    def __init__(self) -> None:
        self._by_object: dict[str, ProcessInstance] = {}

    def get(self, object_id: str) -> ProcessInstance | None:
        return self._by_object.get(object_id)

    def add(self, instance: ProcessInstance) -> None:
        self._by_object[instance.object_id] = instance

    def all(self) -> Iterable[ProcessInstance]:
        return tuple(self._by_object.values())


class ProcessEngine:
    """Общий табличный автомат, не знающий имён конкретного варианта."""

    def __init__(
        self,
        registry: ClassRegistry,
        objects: dict[str, DomainObject],
        users: dict[str, User],
        templates: TemplateCatalog,
        aggregates: AggregateRegistry,
    ) -> None:
        self.registry = registry
        self.objects = objects
        self.users = users
        self.templates = templates
        self.aggregates = aggregates
        self.repository = ProcessRepository()

    def start(self, user_id: str, object_id: str) -> CommandResult:
        user = self.users.get(user_id)
        if user is None:
            return _rejected(
                "user_not_found",
                f"Пользователь {user_id!r} не найден",
            )

        obj = self.objects.get(object_id)
        if obj is None:
            return _rejected(
                "object_not_found",
                f"Объект {object_id!r} не найден",
            )

        template = self.templates.for_class(obj.class_id)
        if template is None:
            return _rejected(
                "template_not_found",
                f"Для класса {obj.class_id!r} нет шаблона процесса",
            )

        existing = self.repository.get(object_id)
        if existing is not None:
            return _rejected(
                "process_already_started",
                "Процесс над этим объектом уже запущен",
                existing.state,
                existing.state,
            )

        if not _has_any_role(user, template.create_roles):
            return _rejected(
                "role_not_allowed",
                f"Для запуска требуется одна из ролей: "
                f"{', '.join(template.create_roles)}",
            )

        instance = ProcessInstance(
            object_id=object_id,
            template_id=template.id,
            state=template.initial_state,
        )
        self.repository.add(instance)
        return CommandResult(
            result="accepted",
            state_before=None,
            state_after=instance.state,
        )

    def act(self, user_id: str, object_id: str, action_id: str) -> CommandResult:
        instance = self.repository.get(object_id)
        user = self.users.get(user_id)

        if user is None:
            state = instance.state if instance is not None else None
            return _rejected(
                "user_not_found",
                f"Пользователь {user_id!r} не найден",
                state,
                state,
            )

        obj = self.objects.get(object_id)
        if obj is None:
            return _rejected(
                "object_not_found",
                f"Объект {object_id!r} не найден",
            )

        if instance is None:
            return _rejected(
                "process_not_started",
                "Процесс над этим объектом не запущен",
            )

        state = instance.state
        template = self.templates.for_class(obj.class_id)
        if template is None:
            return _error(
                "template_not_found",
                f"Для класса {obj.class_id!r} нет шаблона процесса",
                state,
            )

        state_def = template.states.get(state)
        if state_def is None:
            return _error(
                "state_not_found",
                f"Состояние {state!r} отсутствует в шаблоне",
                state,
            )

        if state_def.final:
            return _rejected(
                "process_finished",
                "Процесс уже завершён",
                state,
                state,
            )

        candidates = template.by_key.get((state, action_id), [])
        if not candidates:
            return _rejected(
                "action_not_allowed",
                f"Действие {action_id!r} недопустимо в состоянии {state!r}",
                state,
                state,
            )

        if not _has_any_role(user, state_def.roles):
            return _rejected(
                "role_not_allowed",
                f"В состоянии {state!r} требуется одна из ролей: "
                f"{', '.join(state_def.roles) or '—'}",
                state,
                state,
            )

        context = EvalContext(
            object=obj,
            registry=self.registry,
            objects=self.objects,
            aggregates=self.aggregates,
        )
        matched = [
            transition
            for transition in candidates
            if transition.condition.evaluate(context)
        ]

        if not matched:
            return _rejected(
                "condition_not_met",
                "Условие перехода не выполнено",
                state,
                state,
            )

        if len(matched) > 1:
            return _error(
                "ambiguous_transition",
                "Неоднозначный переход: подходит несколько переходов",
                state,
            )

        target = matched[0].to_state
        instance.state = target
        return CommandResult(
            result="accepted",
            state_before=state,
            state_after=target,
        )


def _has_any_role(user: User, required: Iterable[str]) -> bool:
    required_set = set(required)
    return bool(required_set and (set(user.roles) & required_set))


def _rejected(
    code: str,
    reason: str,
    state_before: str | None = None,
    state_after: str | None = None,
) -> CommandResult:
    return CommandResult(
        result="rejected",
        reason=reason,
        reason_code=code,
        state_before=state_before,
        state_after=state_after,
    )


def _error(
    code: str,
    reason: str,
    state: str | None = None,
) -> CommandResult:
    return CommandResult(
        result="error",
        reason=reason,
        reason_code=code,
        state_before=state,
        state_after=state,
    )
