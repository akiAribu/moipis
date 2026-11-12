"""Загрузка YAML-конфигурации и сборка работающей системы."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .classes import ClassRegistry
from .engine import ProcessEngine
from .errors import ConfigError
from .journal import AuditLog
from .models import DomainObject, User
from .objects import load_objects
from .predicates import AggregateRegistry
from .service import ProcessService
from .templates import TemplateCatalog, load_templates


@dataclass
class Runtime:
    """Все компоненты системы после загрузки конфигурации."""

    config: dict[str, Any]
    registry: ClassRegistry
    objects: dict[str, DomainObject]
    users: dict[str, User]
    roles: dict[str, str]
    templates: TemplateCatalog
    aggregates: AggregateRegistry
    engine: ProcessEngine
    service: ProcessService
    log: AuditLog


def read_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Не удалось прочитать конфигурацию {config_path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Некорректный YAML в {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Корневой элемент конфигурации должен быть объектом")
    return data


def build_runtime(config: dict[str, Any], log: AuditLog) -> Runtime:
    if not isinstance(config, dict):
        raise ConfigError("Конфигурация должна быть объектом")

    roles = _parse_roles(config.get("roles"))
    users = _parse_users(config.get("users"), set(roles))
    registry = ClassRegistry(config.get("classes"))
    objects = load_objects(config.get("objects"), registry)
    aggregates = AggregateRegistry()
    templates = load_templates(
        config.get("processes"),
        registry,
        aggregates,
        set(roles),
    )

    engine = ProcessEngine(
        registry=registry,
        objects=objects,
        users=users,
        templates=templates,
        aggregates=aggregates,
    )
    service = ProcessService(engine, log)

    return Runtime(
        config=config,
        registry=registry,
        objects=objects,
        users=users,
        roles=roles,
        templates=templates,
        aggregates=aggregates,
        engine=engine,
        service=service,
        log=log,
    )


def load_runtime(path: str | Path, log: AuditLog) -> Runtime:
    return build_runtime(read_config(path), log)


def _parse_roles(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ConfigError("Раздел roles должен быть списком")

    roles: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError("Описание роли должно быть объектом")
        role_id = item.get("id")
        if not isinstance(role_id, str) or not role_id:
            raise ConfigError("У роли отсутствует id")
        if role_id in roles:
            raise ConfigError(f"Роль {role_id!r} описана более одного раза")
        roles[role_id] = item.get("title") or role_id
    return roles


def _parse_users(raw: Any, role_ids: set[str]) -> dict[str, User]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ConfigError("Раздел users должен быть списком")

    users: dict[str, User] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError("Описание пользователя должно быть объектом")
        user_id = item.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise ConfigError("У пользователя отсутствует id")
        if user_id in users:
            raise ConfigError(f"Пользователь {user_id!r} описан более одного раза")
        raw_roles = item.get("roles") or []
        if not isinstance(raw_roles, list) or any(
            not isinstance(role, str) for role in raw_roles
        ):
            raise ConfigError(
                f"Пользователь {user_id!r}: roles должен быть списком строк"
            )
        for role_id in raw_roles:
            if role_id not in role_ids:
                raise ConfigError(
                    f"Пользователь {user_id!r}: неизвестная роль {role_id!r}"
                )
        users[user_id] = User(
            id=user_id,
            name=item.get("name") or user_id,
            roles=tuple(raw_roles),
        )
    return users
