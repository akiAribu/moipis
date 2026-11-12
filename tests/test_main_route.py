"""Основной маршрут процесса."""

from __future__ import annotations

from tests.support import act, run, start


def test_main_route_reaches_completed(make_runtime):
    runtime = make_runtime()
    commands = [
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
        act("petrov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("kuznetsov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("smirnov", "order-main", "execute"),
        act("smirnov", "order-main", "complete"),
    ]

    results = run(runtime, *commands)

    assert [result.result for result in results] == ["accepted"] * 8
    assert [result.state_after for result in results] == [
        "registration",
        "composition_approval",
        "price_approval",
        "delivery_approval",
        "payment_approval",
        "execution_decision",
        "execution",
        "completed",
    ]
    assert runtime.engine.repository.get("order-main").state == "completed"
    assert len(runtime.log.records) == 8


def test_correct_returns_to_composition_approval(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
        act("petrov", "order-main", "approve"),
    )

    result = runtime.service.handle(act("sidorov", "order-main", "correct"))

    assert result.accepted
    assert result.state_before == "price_approval"
    assert result.state_after == "composition_approval"
    assert runtime.engine.repository.get("order-main").state == "composition_approval"


def test_express_order_passes_price_by_second_disjunct(make_runtime):
    runtime = make_runtime()
    results = run(
        runtime,
        start("ivanov", "order-express"),
        act("ivanov", "order-express", "submit"),
        act("petrov", "order-express", "approve"),
        act("sidorov", "order-express", "approve"),
    )

    assert all(result.accepted for result in results)
    assert runtime.engine.repository.get("order-express").state == "delivery_approval"
