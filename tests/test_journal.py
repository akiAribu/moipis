"""Проверка журнала и разбора входных команд."""

from __future__ import annotations

import json

from app.journal import JsonLinesLog
from tests.support import act, start


def test_memory_log_contains_success_and_refusal(make_runtime):
    runtime = make_runtime()
    runtime.service.handle(start("ivanov", "order-main"))
    runtime.service.handle(act("petrov", "order-main", "submit"))

    accepted, refused = runtime.log.records

    assert accepted["result"] == "accepted"
    assert accepted["state_before"] is None
    assert accepted["state_after"] == "registration"
    assert accepted["reason"] is None
    assert accepted["command"] == {
        "type": "start",
        "user": "ivanov",
        "object": "order-main",
    }

    assert refused["result"] == "rejected"
    assert refused["state_before"] == "registration"
    assert refused["state_after"] == "registration"
    assert refused["reason"]
    assert refused["reason_code"] == "role_not_allowed"


def test_jsonl_log_is_written_line_by_line(make_runtime, tmp_path):
    path = tmp_path / "journal.jsonl"
    log = JsonLinesLog(path)
    runtime = make_runtime(log=log)
    runtime.service.handle_line("start ivanov order-main")
    runtime.service.handle_line("action ivanov order-main submit")
    log.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert records[0]["state_after"] == "registration"
    assert records[1]["state_after"] == "composition_approval"
    assert all(record["reason"] is None for record in records)


def test_malformed_commands_are_logged(make_runtime):
    runtime = make_runtime()

    text_error = runtime.service.handle_line("action ivanov")
    json_error = runtime.service.handle_line('{"type": "start",')
    unknown_type = runtime.service.handle({"type": "explode"})

    assert text_error.error
    assert json_error.error
    assert unknown_type.error
    assert len(runtime.log.records) == 3
    assert runtime.log.records[0]["command"] == "action ivanov"
    assert runtime.log.records[0]["state_before"] is None
    assert runtime.log.records[1]["command"] == '{"type": "start",'


def test_blank_line_is_not_a_command(make_runtime):
    runtime = make_runtime()

    assert runtime.service.handle_line("   ") is None
    assert runtime.log.records == []


def test_json_command_is_supported(make_runtime):
    runtime = make_runtime()

    result = runtime.service.handle_line(
        '{"type":"start","user":"ivanov","object":"order-main"}'
    )

    assert result.accepted
    assert runtime.engine.repository.get("order-main").state == "registration"
