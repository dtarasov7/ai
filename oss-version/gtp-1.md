Ниже рабочая архитектура, в которой можно надежно видеть:

* смену версии ПО
* появление нового ПО
* удаление ПО
* текущее состояние на любой сервер
* историю изменений в Grafana

## Главная мысль

**Prometheus плохо подходит как единственное хранилище для “снимков состава ПО” и вычисления diff между двумя инвентаризациями.**
Он хорош для:

* текущего состояния
* счетчиков событий
* таймсерий для алертов и графиков

Но для задачи *“что изменилось между двумя сканами”* нужен еще слой **истории инвентаризации** или **слой вычисления изменений**.

Поэтому оптимальная схема такая:

1. **Сканер** на сервере собирает список ПО и версий.
2. **Ansible host** получает результат.
3. Результат сохраняется как **сырой snapshot**.
4. Отдельный **процесс нормализации и diff** сравнивает новый snapshot с предыдущим.
5. В Prometheus публикуются:

   * текущий состав ПО
   * события изменений
6. В Grafana:

   * панель текущего состояния
   * панель изменений
   * таблица последних событий
   * при необходимости алерты

---

# 1. Целевая архитектура

## Вариант, который я рекомендую

### Компоненты

**1. Discovery role / scanner**

* Bash-скрипт на целевом сервере
* ищет opensource ПО и версии
* возвращает структурированный результат

**2. Collector на ansible host**

* принимает результаты со всех серверов
* сохраняет:

  * исходный CSV/JSON
  * нормализованный snapshot

**3. Inventory history storage**
Лучше хранить историю не только в `.prom`, а в одном из вариантов:

* PostgreSQL
* SQLite для старта
* либо versioned JSON/CSV в object storage / файловой системе

Рекомендация:

* **PostgreSQL**, если серверов много и нужен нормальный diff/reporting
* **SQLite**, если решение небольшое и автономное

**4. Diff engine**

* сравнивает:

  * `previous snapshot`
  * `current snapshot`
* определяет:

  * added
  * removed
  * version_changed

**5. Metrics exporter**
Формирует `.prom` для node-exporter textfile collector
или отдает `/metrics` отдельным exporter-сервисом

**6. Prometheus**

* скрапит метрики

**7. Grafana**

* показывает:

  * текущий инвентарь
  * изменения по времени
  * последние изменения
  * статистику по типам изменений

---

# 2. Почему одного общего CSV или одного .prom недостаточно

Если вы просто формируете общий CSV или текущее `.prom`, то вы видите только **текущий факт**:

* на сервере `srv1` есть `nginx 1.24.0`

Но не видно автоматически:

* что вчера был `1.22.1`
* что пакет появился сегодня
* что пакет удалили два дня назад

Для этого нужно либо:

## Подход A. Хранить историю снимков

И сравнивать snapshots между собой

или

## Подход B. При каждом новом скане генерировать события изменений

И сохранять эти события как отдельные метрики/логи

На практике лучше **A + B вместе**:

* история нужна для надежности и ретроспективы
* события удобны для Grafana и alerting

---

# 3. Рекомендуемый формат данных

CSV можно оставить как технический артефакт, но **внутренний канонический формат** лучше сделать JSON.

## Канонический объект записи

```json
{
  "host": "srv-01",
  "software_name": "nginx",
  "version": "1.24.0",
  "source": "binary --version",
  "scan_time": "2026-04-07T10:15:00Z"
}
```

## Нормализованный ключ сущности

Уникальность лучше определять по:

```text
(host, software_name)
```

Если на одном сервере возможны несколько инсталляций одного ПО, тогда:

```text
(host, software_name, install_path)
```

или

```text
(host, software_name, package_manager_name)
```

Иначе diff будет неточным.

---

# 4. Модель хранения истории

## Таблица snapshots

`snapshots`

* `id`
* `host`
* `scan_time`
* `scan_id`
* `status` (success/failed)
* `raw_file_path`
* `checksum`

## Таблица software_inventory

`software_inventory`

* `snapshot_id`
* `host`
* `software_name`
* `version`
* `install_path` nullable
* `vendor` nullable
* `discovery_method`

## Таблица software_changes

`software_changes`

* `id`
* `host`
* `software_name`
* `change_type` (`added`, `removed`, `updated`)
* `old_version` nullable
* `new_version` nullable
* `detected_at`
* `scan_id`
* `previous_scan_id`

Это даст:

* аудит
* удобную выгрузку в Grafana
* базу для повторного формирования метрик

---

# 5. Логика diff

Для каждого нового scan по конкретному серверу:

1. Берем предыдущий успешный snapshot этого сервера
2. Строим словарь:

```text
key = (software_name[, install_path])
value = version
```

3. Сравниваем

## Правила

### Добавление

Ключа не было, теперь есть

```text
prev: absent
curr: present
=> added
```

### Удаление

Ключ был, теперь отсутствует

```text
prev: present
curr: absent
=> removed
```

### Смена версии

Ключ был и остался, но версия изменилась

```text
prev.version != curr.version
=> updated
```

### Без изменений

Ключ есть в обеих версиях, версия та же

---

# 6. Какие метрики отдавать в Prometheus

Нужно разделить метрики на 2 класса:

## A. Текущее состояние

## B. События изменений

---

## A. Метрики текущего состояния

### 1. Наличие ПО на сервере

```prometheus
oss_software_installed{host="srv-01",software="nginx",version="1.24.0"} 1
oss_software_installed{host="srv-01",software="postgresql",version="16.2"} 1
```

Это позволит:

* показать, что установлено сейчас
* фильтровать по серверу/ПО/версии

Важно: при смене версии старая серия должна исчезнуть, новая появиться.

### 2. Время последнего успешного скана

```prometheus
oss_scan_timestamp_seconds{host="srv-01"} 1712484900
```

### 3. Статус скана

```prometheus
oss_scan_success{host="srv-01"} 1
```

### 4. Количество найденных пакетов

```prometheus
oss_software_total{host="srv-01"} 42
```

---

## B. Метрики событий изменений

Здесь лучше использовать **счетчики**.

### 1. Добавления

```prometheus
oss_software_changes_total{host="srv-01",software="nginx",change_type="added"} 1
```

### 2. Удаления

```prometheus
oss_software_changes_total{host="srv-01",software="nginx",change_type="removed"} 1
```

### 3. Обновления версии

```prometheus
oss_software_changes_total{host="srv-01",software="nginx",change_type="updated",old_version="1.22.1",new_version="1.24.0"} 1
```

Но здесь есть важный нюанс:

**Не стоит злоупотреблять label’ами `old_version` и `new_version`, если уникальных комбинаций будет очень много.**
Это увеличит cardinality.

Лучше так:

```prometheus
oss_software_changes_total{host="srv-01",software="nginx",change_type="updated"} 7
```

А подробности версий хранить:

* в БД
* или в Loki как event log

---

# 7. Лучший практический компромисс: Prometheus + Loki

Если нужна хорошая панель изменений в Grafana, очень удобно сделать так:

## В Prometheus

держать:

* текущее состояние
* счетчики изменений
* timestamp последнего скана

## В Loki

писать подробные события:

```json
{
  "host": "srv-01",
  "software": "nginx",
  "change_type": "updated",
  "old_version": "1.22.1",
  "new_version": "1.24.0",
  "detected_at": "2026-04-07T10:15:00Z"
}
```

Тогда в Grafana можно:

* строить графики из Prometheus
* делать таблицу точных событий из Loki

Это намного удобнее, чем пытаться запихнуть детальное событие целиком в labels метрики.

---

# 8. Итоговая рекомендуемая схема

## Минимально правильная

* хранить каждый snapshot
* сравнивать с предыдущим
* генерировать `.prom` с текущим состоянием
* генерировать `.prom` со счетчиками изменений

## Оптимальная

* snapshot history в PostgreSQL
* exporter для Prometheus
* подробные change events в Loki
* Grafana поверх Prometheus + Loki

---

# 9. Поток обработки

## Шаг 1

Ansible role запускает bash-скрипт на сервере

## Шаг 2

Скрипт возвращает JSON/CSV

## Шаг 3

Ansible host сохраняет raw snapshot:

```text
/data/software_inventory/raw/<host>/<timestamp>.json
```

## Шаг 4

Нормализатор приводит имена ПО к каноническому виду:

* `postgres`, `postgresql` → `postgresql`
* `nginx version`, `nginx` → `nginx`

Иначе изменения будут ложными.

## Шаг 5

Diff engine сравнивает прошлый и текущий snapshot

## Шаг 6

Результат пишет:

* в БД историю
* в `.prom` текущее состояние
* в `.prom` агрегированные change counters
* в Loki подробные события

## Шаг 7

Prometheus скрапит node-exporter textfile collector

## Шаг 8

Grafana показывает:

* инвентарь
* изменения
* последние события

---

# 10. Как формировать .prom

Лучше не один файл на сервер, а два логических набора.

## 1. Current state

Например:

```prometheus
oss_software_installed{host="srv-01",software="nginx",version="1.24.0"} 1
oss_software_installed{host="srv-01",software="git",version="2.43.0"} 1
oss_software_total{host="srv-01"} 2
oss_scan_success{host="srv-01"} 1
oss_scan_timestamp_seconds{host="srv-01"} 1712484900
```

## 2. Change stats

Например:

```prometheus
oss_software_changes_total{host="srv-01",change_type="added"} 3
oss_software_changes_total{host="srv-01",change_type="removed"} 1
oss_software_changes_total{host="srv-01",change_type="updated"} 5
oss_last_change_timestamp_seconds{host="srv-01"} 1712484900
```

И опционально по software:

```prometheus
oss_software_change_events_total{host="srv-01",software="nginx",change_type="updated"} 2
```

Но здесь надо следить за cardinality.

---

# 11. Что показать в Grafana

## Панель 1. Текущее состояние

**Table panel**

Поля:

* host
* software
* version
* last_scan_time

Источник:

* Prometheus, метрика `oss_software_installed`

Использовать labels:

* `host`
* `software`
* `version`

---

## Панель 2. Изменения по времени

**Time series / bar chart**

Метрика:

```promql
sum by (change_type) (increase(oss_software_changes_total[24h]))
```

Покажет:

* сколько добавлений
* сколько удалений
* сколько обновлений
  за последние 24 часа

---

## Панель 3. Изменения по серверам

```promql
sum by (host, change_type) (increase(oss_software_changes_total[24h]))
```

---

## Панель 4. Серверы без свежего скана

```promql
time() - oss_scan_timestamp_seconds
```

Можно подсветить те, где значение больше порога.

---

## Панель 5. Последние события изменений

Лучше из Loki или SQL datasource.

Колонки:

* time
* host
* software
* change_type
* old_version
* new_version

Это самая полезная панель для операторов.

---

## Панель 6. ПО, меняющееся чаще всего

```promql
topk(10, sum by (software) (increase(oss_software_change_events_total[30d])))
```

---

# 12. Как не сломать Prometheus высокой кардинальностью

Нельзя бездумно добавлять labels:

* host
* software
* version
* old_version
* new_version
* path
* source
* distro
* package_manager
* build

Иначе будет очень много time series.

## Рекомендация

### В Prometheus оставить labels:

* `host`
* `software`
* `version` — только для current state
* `change_type` — для counters

### Не хранить в Prometheus:

* `old_version`
* `new_version`
* `install_path`
* длинные описания

Это в БД или Loki.

---

# 13. Практический дизайн по уровням зрелости

## Уровень 1. Быстрый старт

Без БД, только filesystem + `.prom`

### Хранение

* raw CSV/JSON по каждому серверу и времени
* symlink/current snapshot на последний файл

### Diff

* Python-скрипт на ansible host сравнивает текущий и предыдущий JSON

### Выход

* `.prom` с current state
* `.prom` со счетчиками изменений

### Минусы

* сложнее строить детальные historical reports
* неудобно расследовать старые изменения

---

## Уровень 2. Нормальный production

**PostgreSQL + Prometheus + Grafana**

### Плюсы

* надежная история
* удобный diff
* SQL datasource в Grafana
* можно строить таблицы “что изменилось”

### Выход

* в Prometheus только агрегаты и текущее состояние
* детали через SQL datasource

---

## Уровень 3. Лучший observability-вариант

**PostgreSQL + Prometheus + Loki + Grafana**

### Плюсы

* Prometheus для графиков и алертов
* Loki для event log
* PostgreSQL для инвентарной истории и отчетов

---

# 14. Алерты

Очень полезно добавить:

## 1. ПО изменилось на критичных хостах

Если за последний час были изменения:

```promql
increase(oss_software_changes_total{host=~"prod-.*"}[1h]) > 0
```

## 2. Нет свежего скана

```promql
time() - oss_scan_timestamp_seconds > 86400
```

## 3. Скан завершился ошибкой

```promql
oss_scan_success == 0
```

---

# 15. Что важно предусмотреть заранее

## Нормализация имен

Иначе получите ложные diff.

## Устойчивый порядок и формат версий

Например:

* `1.2`
* `v1.2`
* `1.2.0`

Лучше нормализовать.

## Идентификация одного и того же ПО

Если ПО находится в разных путях, надо решить:

* считать это одной установкой
* или разными экземплярами

## Идемпотентность

Повторный запуск с тем же snapshot не должен создавать новое событие.

Для этого используйте checksum snapshot-а.

## Обработка неполных данных

Если сканер временно не нашел часть ПО из-за ошибки, можно получить ложное “removed”.

Полезно:

* хранить `scan_status`
* не делать diff, если скан неполный
* либо помечать такие diff как suspect

---

# 16. Рекомендуемая реализация

Я бы предложил такую конкретную схему:

## На целевом хосте

Bash-скрипт собирает данные и выводит **JSON**, не CSV.

## На ansible host

Python-сервис или cron-job:

1. сохраняет raw JSON
2. нормализует данные
3. пишет snapshot в PostgreSQL
4. сравнивает с прошлым snapshot
5. пишет change events в PostgreSQL
6. генерирует `.prom` для node-exporter
7. опционально пишет события в Loki

---

# 17. Пример структуры директорий

```text
/opt/oss-inventory/
  raw/
    srv-01/
      2026-04-07T10:15:00Z.json
  processed/
    current/
      srv-01.json
  textfile_collector/
    oss_inventory.prom
    oss_changes.prom
```

---

# 18. Какой datasource использовать в Grafana

## Для текущего состояния

Prometheus

## Для детальной таблицы изменений

Лучше:

* PostgreSQL datasource
  или
* Loki datasource

---

# 19. Короткий вывод по архитектуре

## Рекомендованное решение

**Не ограничиваться только CSV и `.prom`.**

Сделать 3 слоя:

### 1. Сбор

* bash scanner
* ansible доставляет snapshot

### 2. История и diff

* хранение snapshots
* вычисление added/removed/updated

### 3. Визуализация

* Prometheus: текущее состояние и counters
* Grafana: overview и trends
* PostgreSQL/Loki: детальная история изменений

---

# 20. Самая практичная итоговая схема

Если нужен баланс между простотой и качеством:

**Bash scanner → Ansible host → Python diff service → PostgreSQL → `.prom` → Prometheus → Grafana**

И дополнительно:

**Python diff service → Loki** для подробных event logs.

---

Могу следующим сообщением дать уже **конкретную схему метрик, DDL таблиц PostgreSQL и набор Grafana panels/PromQL запросов** в готовом виде.

