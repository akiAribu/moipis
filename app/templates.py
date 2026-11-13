"""Загрузка шаблонов процессов и каталог шаблонов."""

from __future__ import annotations

from typing import Any

from .classes import ClassRegistry
from .errors import ConfigError
from .expressions import Expression, compile_condition
from .models import ProcessTemplate, StateDef, TransitionDef
from .predicates import AggregateRegistry, Predicate

_ALLOWED_OPS = {"filled", "=", "!=", "<", "<=", ">", ">=", "in_range", "class"}
_NUMERIC_OPS = {"<", "<=", ">", ">="}


class TemplateCatalog:
    """Хранит шаблоны и находит их по точному классу объекта."""

    def __init__(self, templates: list[ProcessTemplate]):
        self._by_class: dict[str, ProcessTemplate] = {}
        for template in templates:
            if template.class_id in self._by_class:
                raise ConfigError(
                    f"Для класса {template.class_id!r} описано более одного шаблона"
                )
            self._by_class[template.class_id] = template

    def for_class(self, class_id: str) -> ProcessTemplate | None:
        return self._by_class.get(class_id)

    def all(self) -> tuple[ProcessTemplate, ...]:
        return tuple(self._by_class.values())


def load_templates(
    raw_processes: list[dict[str, Any]] | None,
    registry: ClassRegistry,
    aggregates: AggregateRegistry,
    role_ids: set[str],
) -> TemplateCatalog:
    if raw_processes is None:
        raw_processes = []
    if not isinstance(raw_processes, list):
        raise ConfigError("Раздел processes должен быть списком")

    templates: list[ProcessTemplate] = []
    for raw in raw_processes:
        templates.append(
            _load_template(raw, registry, aggregates, role_ids)
        )
    return TemplateCatalog(templates)


def _load_template(
    raw: Any,
    registry: ClassRegistry,
    aggregates: AggregateRegistry,
    role_ids: set[str],
) -> ProcessTemplate:
    if not isinstance(raw, dict):
        raise ConfigError("Описание процесса должно быть объектом")

    template_id = raw.get("id")
    if not isinstance(template_id, str) or not template_id:
        raise ConfigError("У шаблона процесса отсутствует id")
    class_id = raw.get("class")
    if not isinstance(class_id, str) or not class_id:
        raise ConfigError(f"Шаблон {template_id!r}: не указан класс")
    if class_id not in registry.class_ids():
        raise ConfigError(
            f"Шаблон {template_id!r}: неизвестный класс {class_id!r}"
        )

    title = raw.get("title") or template_id

    create_roles = _parse_roles(
        raw.get("create_roles"), role_ids, f"Шаблон {template_id!r}: create_roles"
    )
    if not create_roles:
        raise ConfigError(f"Шаблон {template_id!r}: create_roles не может быть пустым")

    actions = _parse_actions(template_id, raw.get("actions"))
    states, initial_state = _parse_states(template_id, raw.get("states"), role_ids)
    predicates = _parse_predicates(
        template_id, raw.get("predicates"), class_id, registry, aggregates
    )
    transitions = _parse_transitions(
        template_id, raw.get("transitions"), actions, states, predicates
    )

    by_key: dict[tuple[str, str], list[TransitionDef]] = {}
    for transition in transitions:
        by_key.setdefault(
            (transition.from_state, transition.action), []
        ).append(transition)

    return ProcessTemplate(
        id=template_id,
        title=title,
        class_id=class_id,
        create_roles=create_roles,
        actions=actions,
        states=states,
        initial_state=initial_state,
        transitions=transitions,
        by_key=by_key,
    )


def _parse_roles(raw: Any, role_ids: set[str], where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ConfigError(f"{where} должен быть списком строк")
    for role_id in raw:
        if role_id not in role_ids:
            raise ConfigError(f"{where}: неизвестная роль {role_id!r}")
    return tuple(raw)


def _parse_actions(
    template_id: str,
    raw: Any,
) -> dict[str, str]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"Шаблон {template_id!r}: actions должен быть непустым списком")
    actions: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError(f"Шаблон {template_id!r}: действие должно быть объектом")
        action_id = item.get("id")
        if not isinstance(action_id, str) or not action_id:
            raise ConfigError(f"Шаблон {template_id!r}: у действия отсутствует id")
        if action_id in actions:
            raise ConfigError(
                f"Шаблон {template_id!r}: действие {action_id!r} описано дважды"
            )
        actions[action_id] = item.get("title") or action_id
    return actions


def _parse_states(
    template_id: str,
    raw: Any,
    role_ids: set[str],
) -> tuple[dict[str, StateDef], str]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"Шаблон {template_id!r}: states должен быть непустым списком")

    states: dict[str, StateDef] = {}
    initial: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError(f"Шаблон {template_id!r}: состояние должно быть объектом")
        state_id = item.get("id")
        if not isinstance(state_id, str) or not state_id:
            raise ConfigError(f"Шаблон {template_id!r}: у состояния отсутствует id")
        if state_id in states:
            raise ConfigError(
                f"Шаблон {template_id!r}: состояние {state_id!r} описано дважды"
            )
        is_initial = bool(item.get("initial", False))
        is_final = bool(item.get("final", False))
        roles = _parse_roles(
            item.get("roles"),
            role_ids,
            f"Шаблон {template_id!r}, состояние {state_id!r}",
        )
        state = StateDef(
            id=state_id,
            title=item.get("title") or state_id,
            initial=is_initial,
            final=is_final,
            roles=roles,
        )
        states[state_id] = state
        if is_initial:
            initial.append(state_id)

    if len(initial) != 1:
        raise ConfigError(
            f"Шаблон {template_id!r}: должно быть ровно одно начальное состояние, "
            f"найдено {len(initial)}"
        )

    return states, initial[0]


def _parse_predicates(
    template_id: str,
    raw: Any,
    template_class: str,
    registry: ClassRegistry,
    aggregates: AggregateRegistry,
) -> dict[str, Predicate]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ConfigError(f"Шаблон {template_id!r}: predicates должен быть списком")

    predicates: dict[str, Predicate] = {}
    for item in raw:
        predicate = _parse_predicate(
            template_id, item, template_class, registry, aggregates
        )
        if predicate.id in predicates:
            raise ConfigError(
                f"Шаблон {template_id!r}: предикат {predicate.id!r} описан дважды"
            )
        predicates[predicate.id] = predicate
    return predicates


def _parse_predicate(
    template_id: str,
    raw: Any,
    template_class: str,
    registry: ClassRegistry,
    aggregates: AggregateRegistry,
) -> Predicate:
    if not isinstance(raw, dict):
        raise ConfigError(f"Шаблон {template_id!r}: предикат должен быть объектом")
    predicate_id = raw.get("id")
    if not isinstance(predicate_id, str) or not predicate_id:
        raise ConfigError(f"Шаблон {template_id!r}: у предиката отсутствует id")
    op = raw.get("op")
    if op not in _ALLOWED_OPS:
        raise ConfigError(
            f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
            f"неподдерживаемый оператор {op!r}"
        )

    if op == "class":
        class_id = raw.get("class")
        if not isinstance(class_id, str) or not class_id:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                "для оператора class нужно указать class"
            )
        if class_id not in registry.class_ids():
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                f"неизвестный класс {class_id!r}"
            )
        return Predicate(id=predicate_id, op=op, class_id=class_id)

    param = raw.get("param")
    if not isinstance(param, str) or not param:
        raise ConfigError(
            f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
            "не указан param"
        )

    aggregate_name: str | None = None
    if "." in param:
        head, tail = param.split(".", 1)
        if not head or not tail or "." in tail:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                "путь состава поддерживает только один уровень вложенности"
            )
        head_param = registry.param(template_class, head)
        if head_param is None or head_param.type != "composition":
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                f"{head!r} не является параметром-составом класса {template_class!r}"
            )
        tail_param = registry.param(head_param.ref_class or "", tail)
        if tail_param is None:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                f"у класса {head_param.ref_class!r} нет параметра {tail!r}"
            )
        aggregate_name = raw.get("aggregate")
        if not isinstance(aggregate_name, str) or not aggregate_name:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                "для пути состава обязателен aggregate"
            )
        aggregates.get(aggregate_name)
        value_param = tail_param
    else:
        param_def = registry.param(template_class, param)
        if param_def is None:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                f"у класса {template_class!r} нет параметра {param!r}"
            )
        value_param = param_def

    if op == "in_range":
        if value_param.type not in {"integer", "decimal", "composition"}:
            raise ConfigError(
                f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
                "in_range применим к числу или составу"
            )
        return Predicate(
            id=predicate_id,
            op=op,
            param=param,
            aggregate=aggregate_name,
        )

    if op == "filled":
        return Predicate(
            id=predicate_id,
            op=op,
            param=param,
            aggregate=aggregate_name,
        )

    if "value" not in raw:
        raise ConfigError(
            f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
            f"для оператора {op!r} нужно указать value"
        )
    value = raw["value"]
    if op in _NUMERIC_OPS and not _is_number(value):
        raise ConfigError(
            f"Шаблон {template_id!r}, предикат {predicate_id!r}: "
            f"для оператора {op!r} value должно быть числом"
        )
    return Predicate(
        id=predicate_id,
        op=op,
        param=param,
        value=value,
        aggregate=aggregate_name,
    )


def _parse_transitions(
    template_id: str,
    raw: Any,
    actions: dict[str, str],
    states: dict[str, StateDef],
    predicates: dict[str, Predicate],
) -> list[TransitionDef]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            f"Шаблон {template_id!r}: transitions должен быть непустым списком"
        )

    transitions: list[TransitionDef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError(f"Шаблон {template_id!r}: переход должен быть объектом")
        from_state = item.get("from")
        action = item.get("action")
        to_state = item.get("to")
        if from_state not in states:
            raise ConfigError(
                f"Шаблон {template_id!r}: переход из неизвестного состояния "
                f"{from_state!r}"
            )
        if to_state not in states:
            raise ConfigError(
                f"Шаблон {template_id!r}: переход в неизвестное состояние "
                f"{to_state!r}"
            )
        if action not in actions:
            raise ConfigError(
                f"Шаблон {template_id!r}: переход использует неизвестное действие "
                f"{action!r}"
            )
        condition: Expression = compile_condition(item.get("condition"), predicates)
        transitions.append(
            TransitionDef(
                from_state=from_state,
                action=action,
                to_state=to_state,
                condition=condition,
            )
        )
    return transitions


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
