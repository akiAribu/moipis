"""Проверка операторов, путей состава и агрегаторов."""

from __future__ import annotations

import copy

from app.models import DomainObject
from app.predicates import EvalContext, Predicate


def context(runtime, object_id: str) -> EvalContext:
    return EvalContext(
        object=runtime.objects[object_id],
        registry=runtime.registry,
        objects=runtime.objects,
        aggregates=runtime.aggregates,
    )


def predicate(**kwargs) -> Predicate:
    return Predicate(**kwargs)


def test_filled_distinguishes_missing_and_empty_string(make_runtime):
    runtime = make_runtime()

    assert predicate(id="p", op="filled", param="priority").evaluate(
        context(runtime, "order-main")
    )
    assert not predicate(id="p", op="filled", param="priority").evaluate(
        context(runtime, "order-null-priority")
    )

    empty_string = DomainObject(
        id="tmp",
        class_id="purchase_order",
        values={"priority": ""},
    )
    ctx = EvalContext(
        object=empty_string,
        registry=runtime.registry,
        objects=runtime.objects,
        aggregates=runtime.aggregates,
    )
    assert predicate(id="p", op="filled", param="priority").evaluate(ctx)


def test_comparison_operators(make_runtime):
    runtime = make_runtime()
    ctx = context(runtime, "order-main")

    assert predicate(
        id="p", op="=", param="total_amount", value=250000
    ).evaluate(ctx)
    assert predicate(
        id="p", op="!=", param="total_amount", value=1
    ).evaluate(ctx)
    assert predicate(
        id="p", op=">", param="total_amount", value=100000
    ).evaluate(ctx)
    assert predicate(
        id="p", op=">=", param="total_amount", value=250000
    ).evaluate(ctx)
    assert predicate(
        id="p", op="<", param="total_amount", value=100000
    ).evaluate(ctx) is False
    assert predicate(
        id="p", op="<=", param="total_amount", value=250000
    ).evaluate(ctx)


def test_undefined_value_makes_comparison_false(make_runtime):
    runtime = make_runtime()
    obj = DomainObject(
        id="tmp",
        class_id="purchase_order",
        values={"total_amount": None},
    )
    ctx = EvalContext(
        object=obj,
        registry=runtime.registry,
        objects=runtime.objects,
        aggregates=runtime.aggregates,
    )

    assert not predicate(
        id="p", op="!=", param="total_amount", value=1
    ).evaluate(ctx)
    assert not predicate(
        id="p", op="filled", param="total_amount"
    ).evaluate(ctx)


def test_in_range_scalar_and_composition(make_runtime):
    runtime = make_runtime()

    assert predicate(
        id="p", op="in_range", param="total_amount"
    ).evaluate(context(runtime, "order-main"))
    assert not predicate(
        id="p", op="in_range", param="total_amount"
    ).evaluate(context(runtime, "order-over-limit"))

    assert predicate(
        id="p", op="in_range", param="items"
    ).evaluate(context(runtime, "order-main"))
    assert not predicate(
        id="p", op="in_range", param="items"
    ).evaluate(context(runtime, "order-empty-items"))


def test_path_aggregate_all_and_any(make_runtime):
    runtime = make_runtime()

    all_items = predicate(
        id="p",
        op="in_range",
        param="items.quantity",
        aggregate="all",
    )
    any_items = predicate(
        id="p",
        op="in_range",
        param="items.quantity",
        aggregate="any",
    )

    assert all_items.evaluate(context(runtime, "order-main"))
    assert not all_items.evaluate(context(runtime, "order-bad-items"))
    assert any_items.evaluate(context(runtime, "order-bad-items"))

    assert all_items.evaluate(context(runtime, "order-empty-items"))
    assert not any_items.evaluate(context(runtime, "order-empty-items"))


def test_inheritance_override_is_used_by_in_range(make_runtime):
    runtime = make_runtime()

    assert not predicate(
        id="p", op="in_range", param="delivery_days"
    ).evaluate(context(runtime, "order-long-delivery"))
    assert predicate(
        id="p", op="in_range", param="delivery_days"
    ).evaluate(context(runtime, "order-main"))


def test_class_predicate(make_runtime):
    runtime = make_runtime()
    pred = predicate(id="p", op="class", class_id="purchase_order")

    assert pred.evaluate(context(runtime, "order-main"))
    assert not pred.evaluate(context(runtime, "item-1"))


def test_composition_comparisons_use_length(make_runtime):
    runtime = make_runtime()
    ctx = context(runtime, "order-main")
    empty = context(runtime, "order-empty-items")

    assert predicate(id="p", op="=", param="items", value=2).evaluate(ctx)
    assert predicate(id="p", op=">", param="items", value=1).evaluate(ctx)
    assert not predicate(id="p", op="<", param="items", value=2).evaluate(ctx)
    assert predicate(id="p", op="=", param="items", value=0).evaluate(empty)
    assert not predicate(id="p", op=">", param="items", value=0).evaluate(empty)


def test_missing_range_boundary_is_not_checked(make_runtime):
    runtime = make_runtime()

    # unit_price: min задан, max отсутствует; верхняя граница не проверяется.
    assert predicate(id="p", op="in_range", param="unit_price").evaluate(
        context(runtime, "item-1")
    )


def test_empty_and_null_composition_are_not_filled(make_runtime):
    runtime = make_runtime()

    for object_id in (
        "order-empty-items",
        "order-missing-items",
        "order-null-items",
    ):
        ctx = context(runtime, object_id)
        assert not predicate(id="p", op="filled", param="items").evaluate(ctx)
        assert predicate(id="p", op="=", param="items", value=0).evaluate(ctx)


def test_path_in_range_uses_subclass_range(make_runtime, base_config):
    config = copy.deepcopy(base_config)
    config["classes"].append(
        {
            "id": "special_item",
            "title": "Специальная позиция",
            "parent": "order_item",
            "params": [
                {
                    "id": "quantity",
                    "title": "Количество",
                    "type": "integer",
                    "min": 1,
                    "max": 5,
                }
            ],
        }
    )
    config["objects"].extend(
        [
            {
                "id": "special-ok",
                "class": "special_item",
                "values": {
                    "product_code": "S-1",
                    "quantity": 5,
                    "unit_price": 10,
                },
            },
            {
                "id": "special-bad",
                "class": "special_item",
                "values": {
                    "product_code": "S-2",
                    "quantity": 6,
                    "unit_price": 10,
                },
            },
            {
                "id": "order-special-ok",
                "class": "standard_order",
                "values": {"total_amount": 100000, "items": ["special-ok"]},
            },
            {
                "id": "order-special-bad",
                "class": "standard_order",
                "values": {"total_amount": 100000, "items": ["special-bad"]},
            },
        ]
    )
    runtime = make_runtime(config)
    pred = predicate(
        id="p",
        op="in_range",
        param="items.quantity",
        aggregate="all",
    )

    assert pred.evaluate(context(runtime, "order-special-ok"))
    assert not pred.evaluate(context(runtime, "order-special-bad"))
