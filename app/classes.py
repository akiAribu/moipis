"""Реестр классов предметной области и разрешение наследования."""

from __future__ import annotations

from typing import Any

from .errors import ConfigError
from .models import UNSET, ParamDef

_ALLOWED_PARAM_TYPES = {"string", "number", "composition"}


class ClassRegistry:
    """Хранит описания классов и вычисляет действующие параметры.

    Поддерживается не более одного родителя. Параметр подкласса с тем же
    ID полностью заменяет описание родителя, но должен сохранять тип.
    """

    def __init__(self, raw_classes: list[dict[str, Any]] | None):
        if raw_classes is None:
            raw_classes = []
        if not isinstance(raw_classes, list):
            raise ConfigError("Раздел classes должен быть списком")

        self._raw: dict[str, dict[str, Any]] = {}
        for raw in raw_classes:
            if not isinstance(raw, dict):
                raise ConfigError("Описание класса должно быть объектом")
            class_id = raw.get("id")
            if not isinstance(class_id, str) or not class_id:
                raise ConfigError("У класса отсутствует id")
            if class_id in self._raw:
                raise ConfigError(f"Класс {class_id!r} описан более одного раза")
            self._raw[class_id] = raw

        self._effective: dict[str, dict[str, ParamDef]] = {}
        self._visiting: set[str] = set()

        # Проверяем все классы сразу, чтобы ошибки наследования и составов
        # обнаруживались при загрузке, а не при первом обращении.
        for class_id in self._raw:
            self.effective_params(class_id)

    def class_ids(self) -> tuple[str, ...]:
        return tuple(self._raw)

    def raw(self, class_id: str) -> dict[str, Any]:
        try:
            return self._raw[class_id]
        except KeyError as exc:
            raise ConfigError(f"Неизвестный класс {class_id!r}") from exc

    def effective_params(self, class_id: str) -> dict[str, ParamDef]:
        """Возвращает параметры класса с учётом наследования."""
        if class_id in self._effective:
            return self._effective[class_id]
        if class_id not in self._raw:
            raise ConfigError(f"Неизвестный класс {class_id!r}")
        if class_id in self._visiting:
            raise ConfigError(f"Циклическое наследование классов около {class_id!r}")

        self._visiting.add(class_id)
        try:
            raw = self._raw[class_id]
            parent = raw.get("parent")
            merged: dict[str, ParamDef] = {}
            if parent is not None:
                if not isinstance(parent, str) or not parent:
                    raise ConfigError(f"У класса {class_id!r} некорректный parent")
                if parent not in self._raw:
                    raise ConfigError(
                        f"У класса {class_id!r} неизвестный родитель {parent!r}"
                    )
                merged.update(self.effective_params(parent))

            for raw_param in raw.get("params") or []:
                param = self._parse_param(class_id, raw_param)
                if param.id in merged and merged[param.id].type != param.type:
                    raise ConfigError(
                        f"Класс {class_id!r}: параметр {param.id!r} меняет тип "
                        f"с {merged[param.id].type!r} на {param.type!r}"
                    )
                merged[param.id] = param
        finally:
            self._visiting.remove(class_id)

        self._effective[class_id] = merged
        return merged

    def param(self, class_id: str, param_id: str) -> ParamDef | None:
        return self.effective_params(class_id).get(param_id)

    def is_subclass(self, class_id: str, ancestor_id: str) -> bool:
        """Проверяет, что class_id совпадает с ancestor_id или наследует его."""
        current: str | None = class_id
        seen: set[str] = set()
        while current is not None:
            if current == ancestor_id:
                return True
            if current in seen:
                raise ConfigError(f"Циклическое наследование около {current!r}")
            seen.add(current)
            raw = self._raw.get(current)
            if raw is None:
                raise ConfigError(f"Неизвестный класс {current!r}")
            parent = raw.get("parent")
            current = parent if isinstance(parent, str) else None
        return False

    def _parse_param(self, class_id: str, raw: Any) -> ParamDef:
        if not isinstance(raw, dict):
            raise ConfigError(f"Класс {class_id!r}: параметр должен быть объектом")
        param_id = raw.get("id")
        if not isinstance(param_id, str) or not param_id:
            raise ConfigError(f"Класс {class_id!r}: у параметра отсутствует id")
        title = raw.get("title") or param_id
        param_type = raw.get("type")
        if param_type not in _ALLOWED_PARAM_TYPES:
            raise ConfigError(
                f"Класс {class_id!r}, параметр {param_id!r}: "
                f"неподдерживаемый тип {param_type!r}"
            )

        if param_type == "composition":
            ref_class = raw.get("class")
            if not isinstance(ref_class, str) or not ref_class:
                raise ConfigError(
                    f"Класс {class_id!r}, параметр {param_id!r}: "
                    "для состава нужно указать class"
                )
            if ref_class not in self._raw:
                raise ConfigError(
                    f"Класс {class_id!r}, параметр {param_id!r}: "
                    f"неизвестный класс состава {ref_class!r}"
                )
            quantity_min = raw.get("quantity_min")
            quantity_max = raw.get("quantity_max")
            for name, value in (
                ("quantity_min", quantity_min),
                ("quantity_max", quantity_max),
            ):
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool)
                ):
                    raise ConfigError(
                        f"Класс {class_id!r}, параметр {param_id!r}: "
                        f"{name} должен быть целым числом"
                    )
            if (
                quantity_min is not None
                and quantity_max is not None
                and quantity_min > quantity_max
            ):
                raise ConfigError(
                    f"Класс {class_id!r}, параметр {param_id!r}: "
                    "quantity_min больше quantity_max"
                )
            return ParamDef(
                id=param_id,
                title=title,
                type=param_type,
                ref_class=ref_class,
                quantity_min=quantity_min,
                quantity_max=quantity_max,
            )

        default = raw["default"] if "default" in raw else UNSET
        if param_type == "number":
            min_value = raw.get("min")
            max_value = raw.get("max")
            for name, value in (("min", min_value), ("max", max_value)):
                if value is not None and not _is_number(value):
                    raise ConfigError(
                        f"Класс {class_id!r}, параметр {param_id!r}: "
                        f"{name} должен быть числом"
                    )
            if min_value is not None and max_value is not None and min_value > max_value:
                raise ConfigError(
                    f"Класс {class_id!r}, параметр {param_id!r}: min больше max"
                )
        else:
            min_value = None
            max_value = None

        return ParamDef(
            id=param_id,
            title=title,
            type=param_type,
            min=min_value,
            max=max_value,
            default=default,
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
