"""Интерактивная консоль и запуск сценариев."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Iterable

from .config_loader import Runtime, build_runtime, read_config
from .errors import ConfigError
from .journal import JsonLinesLog
from .models import CommandResult

HELP_TEXT = """\
Команды:
  start <пользователь> <объект>             запустить процесс
  action <пользователь> <объект> <действие>  выполнить действие
  state <объект>                            состояние процесса
  objects                                   список объектов
  users                                     список пользователей и ролей
  processes                                 список запущенных процессов
  help                                      эта справка
  quit                                      выход

Команды start и action можно вводить также в формате JSON:
  {"type":"start","user":"ivanov","object":"order-main"}
  {"type":"action","user":"petrov","object":"order-main","action":"approve"}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app",
        description="Исполнение бизнес-процессов над объектами предметной области",
    )
    parser.add_argument("--config", required=True, help="путь к YAML-конфигурации")
    parser.add_argument(
        "--journal",
        default="var/journal.jsonl",
        help="путь к JSONL-журналу (по умолчанию var/journal.jsonl)",
    )
    parser.add_argument(
        "--script",
        help="файл с командами; без него запускается интерактивная консоль",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "text", "json"),
        default="auto",
        help="формат команд в файле или консоли (по умолчанию auto)",
    )
    args = parser.parse_args(argv)

    try:
        config = read_config(args.config)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    log = JsonLinesLog(args.journal)
    try:
        try:
            runtime = build_runtime(config, log)
        except ConfigError as exc:
            print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
            return 2

        print_summary(runtime)
        if args.script:
            return run_script(runtime, Path(args.script), args.format)
        return run_interactive(runtime, args.format)
    finally:
        log.close()


def print_summary(runtime: Runtime) -> None:
    print(
        "Загружено: "
        f"классов — {len(runtime.registry.class_ids())}, "
        f"объектов — {len(runtime.objects)}, "
        f"пользователей — {len(runtime.users)}, "
        f"шаблонов — {len(runtime.templates.all())}."
    )
    print("Процессов запущено: 0.")


def run_script(runtime: Runtime, path: Path, format: str) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"Не удалось прочитать файл команд {path}: {exc}", file=sys.stderr)
        return 2

    executed = 0
    has_error = False
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        result = runtime.service.handle_line(line, format=format)
        if result is None:
            continue
        executed += 1
        print(f"{number:>3}  {line}")
        print_result(result, indent="     ")
        if result.error:
            has_error = True

    print(f"Выполнено команд: {executed}.")
    return 1 if has_error else 0


def run_interactive(runtime: Runtime, format: str) -> int:
    print("Введите help для справки, quit для выхода.")
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        text = line.strip()
        if not text or text.startswith("#"):
            continue

        parts = _split(text)
        head = parts[0].lower() if parts else ""

        if head in {"quit", "exit"}:
            return 0
        if head in {"help", "?"}:
            print(HELP_TEXT)
            continue
        if head == "state":
            _print_state(runtime, parts)
            continue
        if head == "objects":
            _print_objects(runtime)
            continue
        if head == "users":
            _print_users(runtime)
            continue
        if head == "processes":
            _print_processes(runtime)
            continue

        result = runtime.service.handle_line(text, format=format)
        if result is not None:
            print_result(result)


def print_result(result: CommandResult, indent: str = "") -> None:
    if result.result == "accepted":
        before = result.state_before if result.state_before is not None else "—"
        print(f"{indent}accepted: {before} -> {result.state_after}")
    else:
        print(f"{indent}{result.result}: {result.reason}")


def _split(line: str) -> list[str]:
    try:
        return shlex.split(line)
    except ValueError:
        return []


def _print_state(runtime: Runtime, parts: list[str]) -> None:
    if len(parts) != 2:
        print("Формат команды: state <объект>")
        return
    object_id = parts[1]
    obj = runtime.objects.get(object_id)
    if obj is None:
        print(f"Объект {object_id!r} не найден")
        return
    instance = runtime.engine.repository.get(object_id)
    if instance is None:
        print(f"{object_id}: процесс не запущен")
        return
    template = runtime.templates.for_class(obj.class_id)
    state_title = ""
    if template is not None:
        state_def = template.states.get(instance.state)
        if state_def is not None:
            state_title = f" ({state_def.title})"
    print(f"{object_id}: {instance.state}{state_title}")


def _print_objects(runtime: Runtime) -> None:
    if not runtime.objects:
        print("Объектов нет.")
        return
    for object_id in sorted(runtime.objects):
        obj = runtime.objects[object_id]
        print(f"{object_id}  [{obj.class_id}]")


def _print_users(runtime: Runtime) -> None:
    if not runtime.users:
        print("Пользователей нет.")
        return
    for user_id in sorted(runtime.users):
        user = runtime.users[user_id]
        roles = ", ".join(user.roles) if user.roles else "—"
        print(f"{user_id}  {user.name}  роли: {roles}")


def _print_processes(runtime: Runtime) -> None:
    instances: Iterable = runtime.engine.repository.all()
    instances = tuple(instances)
    if not instances:
        print("Запущенных процессов нет.")
        return
    for instance in sorted(instances, key=lambda item: item.object_id):
        print(f"{instance.object_id}: {instance.state}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
