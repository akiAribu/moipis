"""Проверка загрузки конфигурации и ограничений шаблона."""

from __future__ import annotations

import copy

import pytest

from app.errors import ConfigError
from tests.support import act, run, start


def test_defaults_and_explicit_null(make_runtime):
    runtime = make_runtime()

    defaults = runtime.objects["order-defaults"].values
    assert defaults["priority"] == "normal"
    assert defaults["delivery_days"] == 14
    assert defaults["payment_terms"] == "prepayment"
    assert defaults["items"] == ["item-1"]

    assert runtime.objects["order-null-priority"].values["priority"] is None


def test_inheritance_overrides_parameter_description(make_runtime):
    runtime = make_runtime()

    base = runtime.registry.param("purchase_order", "delivery_days")
    child = runtime.registry.param("standard_order", "delivery_days")

    assert base is not None and child is not None
    assert base.min == 1 and base.max == 60 and base.default == 30
    assert child.min == 1 and child.max == 30 and child.default == 14
    assert runtime.registry.is_subclass("standard_order", "purchase_order")
    assert not runtime.registry.is_subclass("purchase_order", "standard_order")


def test_template_is_not_inherited(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    config["classes"].append(
        {
            "id": "special_order",
            "title": "Специальный заказ",
            "parent": "standard_order",
        }
    )
    config["objects"].append(
        {
            "id": "special-1",
            "class": "special_order",
            "values": {
                "total_amount": 100000,
                "items": ["item-1"],
            },
        }
    )
    runtime = make_runtime(config)

    result = runtime.service.handle(start("ivanov", "special-1"))

    assert result.result == "rejected"
    assert result.reason_code == "template_not_found"


def test_unsupported_aggregate_is_a_config_error(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    predicate = next(
        item
        for item in config["processes"][0]["predicates"]
        if item["id"] == "items_quantity_ok"
    )
    predicate["aggregate"] = "majority"

    with pytest.raises(ConfigError, match="majority"):
        make_runtime(config)


def test_ambiguous_transition_is_an_error(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    config["processes"][0]["transitions"].append(
        {
            "from": "composition_approval",
            "action": "approve",
            "to": "delivery_approval",
        }
    )
    runtime = make_runtime(config)
    run(
        runtime,
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
    )

    result = runtime.service.handle(act("petrov", "order-main", "approve"))

    assert result.result == "error"
    assert result.reason_code == "ambiguous_transition"
    assert result.state_before == "composition_approval"
    assert result.state_after == "composition_approval"
    assert runtime.engine.repository.get("order-main").state == "composition_approval"


def test_exactly_one_initial_state_is_required(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    state = next(
        item
        for item in config["processes"][0]["states"]
        if item["id"] == "price_approval"
    )
    state["initial"] = True

    with pytest.raises(ConfigError, match="начальное состояние"):
        make_runtime(config)


def test_unknown_parameter_in_object_is_rejected(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    order = next(
        item for item in config["objects"] if item["id"] == "order-main"
    )
    order["values"]["unknown_param"] = 1

    with pytest.raises(ConfigError, match="unknown_param"):
        make_runtime(config)
