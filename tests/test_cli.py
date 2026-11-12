"""Проверка интерактивной консоли и режима сценария."""

from __future__ import annotations

import json
from pathlib import Path

from app.cli import main, run_interactive

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "purchase_order.yaml"
DEMO = ROOT / "commands" / "demo.txt"


def test_script_mode_runs_demo(tmp_path):
    journal = tmp_path / "journal.jsonl"

    code = main(
        [
            "--config",
            str(CONFIG),
            "--journal",
            str(journal),
            "--script",
            str(DEMO),
        ]
    )

    assert code == 0
    records = [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 8
    assert records[-1]["state_after"] == "completed"


def test_interactive_console(monkeypatch, capsys, make_runtime):
    runtime = make_runtime()
    commands = iter(
        [
            "start ivanov order-main",
            "action ivanov order-main submit",
            "state order-main",
            "help",
            "quit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(commands))

    code = run_interactive(runtime, "auto")

    output = capsys.readouterr().out
    assert code == 0
    assert "accepted: — -> registration" in output
    assert "accepted: registration -> composition_approval" in output
    assert "order-main: composition_approval" in output
    assert "Команды:" in output
    assert len(runtime.log.records) == 2
