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


def test_process_transitions_match_figure_3(make_runtime):
    runtime = make_runtime()
    template = runtime.templates.for_class("standard_order")
    assert template is not None
    actual = {
        (transition.from_state, transition.action): transition.to_state
        for transition in template.transitions
    }
    expected = {
        ("registration", "submit"): "composition_approval",
        ("composition_approval", "approve"): "price_approval",
        ("composition_approval", "defer"): "deferred_review",
        ("price_approval", "approve"): "delivery_approval",
        ("price_approval", "correct"): "composition_approval",
        ("price_approval", "defer"): "deferred_review",
        ("delivery_approval", "approve"): "payment_approval",
        ("delivery_approval", "correct"): "composition_approval",
        ("delivery_approval", "defer"): "deferred_review",
        ("payment_approval", "approve"): "execution_decision",
        ("payment_approval", "correct"): "composition_approval",
        ("payment_approval", "defer"): "deferred_review",
        ("deferred_review", "resume"): "composition_approval",
        ("execution_decision", "execute"): "execution",
        ("execution_decision", "return"): "composition_approval",
        ("execution_decision", "defer"): "deferred_execution",
        ("deferred_execution", "reconsider"): "execution_decision",
        ("execution", "defer"): "deferred_execution",
        ("execution", "complete"): "completed",
    }

    assert actual == expected


def test_composition_null_and_missing_become_empty(make_runtime):
    runtime = make_runtime()

    assert runtime.objects["order-missing-items"].values["items"] == []
    assert runtime.objects["order-null-items"].values["items"] == []


def test_integer_and_decimal_parameter_types(make_runtime):
    runtime = make_runtime()

    total = runtime.registry.param("purchase_order", "total_amount")
    days = runtime.registry.param("purchase_order", "delivery_days")
    quantity = runtime.registry.param("order_item", "quantity")
    price = runtime.registry.param("order_item", "unit_price")
    child_days = runtime.registry.param("standard_order", "delivery_days")

    assert total is not None and total.type == "decimal"
    assert days is not None and days.type == "integer"
    assert quantity is not None and quantity.type == "integer"
    assert price is not None and price.type == "decimal"
    assert child_days is not None and child_days.type == "integer"


def test_unknown_parameter_type_is_rejected(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    config["classes"][0]["params"][0]["type"] = "number"

    with pytest.raises(ConfigError, match="неподдерживаемый тип"):
        make_runtime(config)


def test_object_value_must_match_parameter_type(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    order = next(
        item for item in config["objects"] if item["id"] == "order-main"
    )
    order["values"]["delivery_days"] = 10.5

    with pytest.raises(ConfigError, match="целым числом"):
        make_runtime(config)


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
