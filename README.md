# Управление заказом на поставку стандартной продукции

Реализация задания 3-1-1 «Приёмы моделирования бизнес-логики», вариант 3.
Система исполняет бизнес-процесс над заранее описанными объектами предметной
области. Классы, параметры, объекты, пользователи, роли и шаблон процесса
задаются в YAML; общий исполнитель не содержит названий состояний, действий и
правил конкретного варианта.

## Требования

- Python 3.12+
- PyYAML
- pytest для запуска тестов

Установка зависимостей:

```bash
python3 -m pip install -r requirements.txt
```

Если система не разрешает установку в системный Python, создайте виртуальное
окружение:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Если создание venv недоступно, а pip сообщает об externally managed
environment, можно установить pytest в пользовательский каталог:

```bash
python3 -m pip install --user --break-system-packages pytest
```

## Быстрый запуск

Интерактивная консоль:

```bash
python -m app --config config/purchase_order.yaml --journal var/journal.jsonl
```

Сценарий из файла:

```bash
python -m app \
  --config config/purchase_order.yaml \
  --journal var/journal.jsonl \
  --script commands/demo.txt
```

Демонстрация отказов и возвратов:

```bash
python -m app \
  --config config/purchase_order.yaml \
  --journal var/journal.jsonl \
  --script commands/refusals.txt
```

Журнал дописывается в конец файла. Для чистого прогона используйте новый путь
или удалите старый журнал.

## Интерактивная консоль

После запуска программа загружает конфигурацию, создаёт объекты и шаблон, но не
запускает процессы. Доступны команды:

```text
start <пользователь> <объект>
action <пользователь> <объект> <действие>
state <объект>
objects
users
processes
help
quit
```

Пример:

```text
> start ivanov order-main
accepted: — -> registration

> action ivanov order-main submit
accepted: registration -> composition_approval

> action petrov order-main approve
accepted: composition_approval -> price_approval

> action petrov order-main approve
rejected: В состоянии 'price_approval' требуется одна из ролей: pricing_department

> quit
```

Команды `start` и `action` можно вводить и в JSON-формате:

```json
{"type":"start","user":"ivanov","object":"order-main"}
{"type":"action","user":"petrov","object":"order-main","action":"approve"}
```

Формат ввода выбирается параметром `--format auto|text|json`. По умолчанию
`auto`: строка, начинающаяся с `{`, разбирается как JSON, остальные — как
текстовая команда.

## Предметная модель

Классы:

- `purchase_order` — базовый заказ: `priority`, `total_amount`,
  `delivery_days`, `payment_terms`;
- `order_item` — позиция заказа: `product_code`, `quantity`, `unit_price`;
- `standard_order` — наследует `purchase_order`, переопределяет
  `delivery_days` диапазоном 1–30 и значением по умолчанию 14, добавляет
  состав `items` из объектов `order_item`.

Реализованы оба механизма объектной модели:

- **наследование параметров** — `standard_order` наследует параметры
  `purchase_order`; переопределённое описание `delivery_days` заменяет
  родительское целиком, тип сохраняется;
- **составность** — `standard_order.items` хранит ссылки на заранее
  загруженные объекты `order_item`; количество проверяется предикатом с
  агрегатором `all`.

Готовые объекты описаны в `config/purchase_order.yaml`. Например,
`order-main` проходит основной маршрут, `order-empty-items` и
`order-bad-items` дают отказ по условию состава, `order-long-delivery`
проверяет переопределённый диапазон срока поставки, `order-express`
проверяет второй дизъюнкт условия цены.

## Шаблон процесса

Состояния: `registration`, `composition_approval`, `price_approval`,
`delivery_approval`, `payment_approval`, `deferred_review`,
`execution_decision`, `execution`, `deferred_execution`, `completed`.

Основной маршрут:

```text
registration
  --submit--> composition_approval
  --approve--> price_approval
  --approve--> delivery_approval
  --approve--> payment_approval
  --approve--> execution_decision
  --execute--> execution
  --complete--> completed
```

Возврат `correct` из согласований цены, поставки и оплаты ведёт обратно в
`composition_approval`. Действие `defer` переводит в отложенные состояния,
`resume` и `reconsider` возвращают процесс к исполнению.

Условия заданы в ДНФ. Например, условие согласования цены:

```text
(amount_ok И prepayment_ok) ИЛИ
(amount_ok И НЕ prepayment_ok И express)
```

Условие состава:

```text
has_items И items_quantity_ok
```

где `items_quantity_ok` проверяет `items.quantity` оператором `in_range` с
агрегатором `all`.

## Обработка команд

Каждая команда проходит один путь:

```text
файл или stdin
  -> CLI
  -> ProcessService.handle
  -> ProcessEngine.start / act
  -> проверки пользователя, объекта, шаблона, процесса, роли и условий
  -> CommandResult
  -> AuditLog (одна запись)
  -> консоль
```

Порядок проверки действия:

1. пользователь и объект существуют;
2. процесс запущен;
3. состояние не конечное;
4. есть переход по паре «состояние, действие»;
5. у пользователя есть роль текущего состояния;
6. условие перехода истинно;
7. подходит ровно один переход.

Если подходит несколько переходов, возвращается ошибка неоднозначности, а
состояние не меняется. При отказе или ошибке состояние также не меняется.

## Журнал

Журнал ведётся в JSONL: один JSON-объект на строку. Записываются успех,
отказ и ошибка, включая некорректные команды. Пример записи:

```json
{
  "command": {"type": "action", "user": "petrov", "object": "order-main", "action": "approve"},
  "user": "petrov",
  "object": "order-main",
  "state_before": "composition_approval",
  "state_after": "composition_approval",
  "result": "rejected",
  "reason": "Условие перехода не выполнено",
  "reason_code": "condition_not_met"
}
```

Поля `state_before` и `state_after` при отказе совпадают. Для успешного запуска
`state_before` равен `null`. При вводе из консоли или файла дополнительно
сохраняется поле `raw` с исходной строкой команды. Журнал не используется для
восстановления процессов: после перезапуска объекты загружаются заново, а
запущенных процессов нет.

## Тесты

```bash
python3 -m pytest -q
```

Тесты проверяют:

- основной маршрут до `completed`;
- возврат `correct` на согласование состава;
- отказ по роли и неизменность состояния;
- отказ по условию для пустого состава и позиции вне диапазона;
- агрегатор `all` и различие `all`/`any`;
- наследование и переопределение `delivery_days`;
- значения по умолчанию и явный `null`;
- повторный запуск и действие в конечном состоянии;
- ветку отложенного рассмотрения;
- экспресс-заказ с постоплатой и превышение суммы;
- неоднозначный переход и неподдерживаемый агрегатор;
- записи журнала в памяти и в JSONL-файле;
- некорректные команды и разбор JSON.

## Структура проекта

```text
app/
  __main__.py        запуск python -m app
  cli.py             интерактивная консоль и режим сценария
  config_loader.py   загрузка YAML и сборка компонентов
  classes.py         реестр классов и наследование
  objects.py         загрузка объектов и составов
  predicates.py      предикаты и агрегаторы
  expressions.py     дерево ДНФ
  templates.py       шаблоны процессов
  engine.py          табличный автомат и экземпляры процессов
  service.py         единая точка обработки команд
  journal.py         JSONL-журнал и журнал в памяти
config/
  purchase_order.yaml
commands/
  demo.txt
  refusals.txt
tests/
```

## Ограничения

- нет графического интерфейса, аутентификации и проверки пароля;
- нет СУБД, очереди и восстановления процессов из журнала;
- рабочие состояния хранятся только в памяти;
- обрабатывается один шаблон процесса;
- составность поддерживает один уровень вложенности;
- полная валидация произвольной конфигурации не выполняется, но критичные
  ошибки (неизвестный агрегатор, дубли шаблонов, отсутствие начального
  состояния, неизвестные ссылки) обнаруживаются при загрузке.
