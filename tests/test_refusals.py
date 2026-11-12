"""Отказы, возвраты и проверки механизмов объектной модели."""

from __future__ import annotations

from tests.support import act, run, start


def test_role_refusal_does_not_change_state(make_runtime):
    runtime = make_runtime()
    run(runtime, start("ivanov", "order-main"))

    result = runtime.service.handle(act("petrov", "order-main", "submit"))

    assert result.result == "rejected"
    assert result.reason_code == "role_not_allowed"
    assert result.state_before == "registration"
    assert result.state_after == "registration"
    assert runtime.engine.repository.get("order-main").state == "registration"


def test_empty_composition_is_rejected(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-empty-items"),
        act("ivanov", "order-empty-items", "submit"),
    )

    result = runtime.service.handle(act("petrov", "order-empty-items", "approve"))

    assert result.result == "rejected"
    assert result.reason_code == "condition_not_met"
    assert result.state_before == "composition_approval"
    assert result.state_after == "composition_approval"


def test_composition_all_rejects_one_bad_item(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-bad-items"),
        act("ivanov", "order-bad-items", "submit"),
    )

    result = runtime.service.handle(act("petrov", "order-bad-items", "approve"))

    assert result.result == "rejected"
    assert result.reason_code == "condition_not_met"
    assert runtime.engine.repository.get("order-bad-items").state == "composition_approval"


def test_inheritance_override_rejects_long_delivery(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-long-delivery"),
        act("ivanov", "order-long-delivery", "submit"),
        act("petrov", "order-long-delivery", "approve"),
        act("sidorov", "order-long-delivery", "approve"),
    )

    result = runtime.service.handle(act("kuznetsov", "order-long-delivery", "approve"))

    assert result.result == "rejected"
    assert result.reason_code == "condition_not_met"
    assert result.state_before == "delivery_approval"
    assert result.state_after == "delivery_approval"


def test_amount_over_limit_is_rejected(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-over-limit"),
        act("ivanov", "order-over-limit", "submit"),
        act("petrov", "order-over-limit", "approve"),
    )

    result = runtime.service.handle(act("sidorov", "order-over-limit", "approve"))

    assert result.result == "rejected"
    assert result.reason_code == "condition_not_met"
    assert result.state_before == "price_approval"
    assert result.state_after == "price_approval"


def test_duplicate_start_is_rejected(make_runtime):
    runtime = make_runtime()
    first = runtime.service.handle(start("ivanov", "order-main"))
    second = runtime.service.handle(start("ivanov", "order-main"))

    assert first.accepted
    assert second.result == "rejected"
    assert second.reason_code == "process_already_started"
    assert second.state_before == "registration"
    assert second.state_after == "registration"


def test_action_in_final_state_is_rejected(make_runtime):
    runtime = make_runtime()
    run(
        runtime,
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
        act("petrov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("kuznetsov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("smirnov", "order-main", "execute"),
        act("smirnov", "order-main", "complete"),
    )

    result = runtime.service.handle(act("smirnov", "order-main", "complete"))

    assert result.result == "rejected"
    assert result.reason_code == "process_finished"
    assert result.state_before == "completed"
    assert result.state_after == "completed"


def test_deferred_review_branch(make_runtime):
    runtime = make_runtime()
    results = run(
        runtime,
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
        act("petrov", "order-main", "defer"),
        act("volkov", "order-main", "resume"),
        act("smirnov", "order-main", "return"),
    )

    assert all(result.accepted for result in results)
    assert runtime.engine.repository.get("order-main").state == "composition_approval"


def test_deferred_execution_branch(make_runtime):
    runtime = make_runtime()
    results = run(
        runtime,
        start("ivanov", "order-main"),
        act("ivanov", "order-main", "submit"),
        act("petrov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("kuznetsov", "order-main", "approve"),
        act("sidorov", "order-main", "approve"),
        act("smirnov", "order-main", "defer"),
        act("smirnov", "order-main", "reconsider"),
        act("smirnov", "order-main", "complete"),
    )

    assert all(result.accepted for result in results)
    assert runtime.engine.repository.get("order-main").state == "completed"


def test_unknown_user_object_and_action(make_runtime):
    runtime = make_runtime()

    unknown_user = runtime.service.handle(start("unknown", "order-main"))
    unknown_object = runtime.service.handle(start("ivanov", "unknown"))
    no_process = runtime.service.handle(act("ivanov", "order-main", "submit"))

    run(runtime, start("ivanov", "order-main"))
    unknown_action = runtime.service.handle(act("ivanov", "order-main", "cancel"))

    assert unknown_user.reason_code == "user_not_found"
    assert unknown_object.reason_code == "object_not_found"
    assert no_process.reason_code == "process_not_started"
    assert unknown_action.reason_code == "action_not_allowed"
    assert unknown_action.state_before == "registration"
    assert unknown_action.state_after == "registration"
