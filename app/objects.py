"""Загрузка готовых объектов предметной области."""

from __future__ import annotations

from typing import Any

from .classes import ClassRegistry
from .errors import ConfigError
from .models import UNSET, DomainObject, ParamDef


def load_objects(
    raw_objects: list[dict[str, Any]] | None,
    registry: ClassRegistry,
) -> dict[str, DomainObject]:
    """Создаёт объекты в памяти и применяет значения по умолчанию.

    Явно указанный null для параметра-состава нормализуется в пустой список:
    по условию задания незаданный состав — это пустой список. Для скалярных
    параметров явный null остаётся незаданным значением.

    Границы min/max и quantity_min/quantity_max при загрузке не проверяются:
    они нужны только предикатам переходов.
    """
    if raw_objects is None:
        raw_objects = []
    if not isinstance(raw_objects, list):
        raise ConfigError("Раздел objects должен быть списком")

    raw_by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_objects:
        if not isinstance(raw, dict):
            raise ConfigError("Описание объекта должно быть объектом")
        object_id = raw.get("id")
        if not isinstance(object_id, str) or not object_id:
            raise ConfigError("У объекта отсутствует id")
        if object_id in raw_by_id:
            raise ConfigError(f"Объект {object_id!r} описан более одного раза")
        raw_by_id[object_id] = raw

    objects: dict[str, DomainObject] = {}
    for object_id, raw in raw_by_id.items():
        class_id = raw.get("class")
        if not isinstance(class_id, str) or not class_id:
            raise ConfigError(f"Объект {object_id!r}: не указан класс")
        params = registry.effective_params(class_id)

        raw_values = raw.get("values") or {}
        if not isinstance(raw_values, dict):
            raise ConfigError(f"Объект {object_id!r}: values должен быть объектом")

        unknown = set(raw_values) - set(params)
        if unknown:
            raise ConfigError(
                f"Объект {object_id!r}: неизвестные параметры {sorted(unknown)}"
            )

        values: dict[str, Any] = {}
        for param_id, param in params.items():
            if param_id in raw_values:
                value = raw_values[param_id]
                if param.type == "composition":
                    if value is None:
                        values[param_id] = []
                    elif isinstance(value, list):
                        values[param_id] = list(value)
                    else:
                        raise ConfigError(
                            f"Объект {object_id!r}: состав {param_id!r} "
                            "должен быть списком ID"
                        )
                elif value is None:
                    values[param_id] = None
                else:
                    _check_value_type(object_id, param, value)
                    values[param_id] = value
            elif param.type == "composition":
                values[param_id] = []
            elif param.default is not UNSET:
                values[param_id] = param.default
            else:
                values[param_id] = None

        objects[object_id] = DomainObject(
            id=object_id, class_id=class_id, values=values
        )

    _validate_composition_refs(objects, registry)
    return objects


def _check_value_type(
    object_id: str,
    param: ParamDef,
    value: Any,
) -> None:
    if param.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(
                f"Объект {object_id!r}: параметр {param.id!r} "
                "должен быть целым числом"
            )
    elif param.type == "decimal":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(
                f"Объект {object_id!r}: параметр {param.id!r} "
                "должен быть числом"
            )
    elif param.type == "string":
        if not isinstance(value, str):
            raise ConfigError(
                f"Объект {object_id!r}: параметр {param.id!r} "
                "должен быть строкой"
            )


def _validate_composition_refs(
    objects: dict[str, DomainObject],
    registry: ClassRegistry,
) -> None:
    for obj in objects.values():
        params = registry.effective_params(obj.class_id)
        for param_id, param in params.items():
            if param.type != "composition":
                continue
            refs = obj.values.get(param_id)
            if refs is None:
                continue
            for ref_id in refs:
                if not isinstance(ref_id, str) or ref_id not in objects:
                    raise ConfigError(
                        f"Объект {obj.id!r}: состав {param_id!r} ссылается "
                        f"на неизвестный объект {ref_id!r}"
                    )
                ref_obj = objects[ref_id]
                if not registry.is_subclass(ref_obj.class_id, param.ref_class or ""):
                    raise ConfigError(
                        f"Объект {obj.id!r}: позиция {ref_id!r} класса "
                        f"{ref_obj.class_id!r} не подходит для состава "
                        f"{param_id!r} (ожидается {param.ref_class!r})"
                    )
