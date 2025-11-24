### Введение в решение

Это решение предназначено для мониторинга и визуализации версий open-source ПО на серверах. Оно позволяет отслеживать текущие версии ПО, историю изменений, время смен версий, а также настраивать алерты на ключевые события (например, обновления или понижения версий). Основные цели:
- Автоматический сбор данных о версиях ПО без вмешательства администраторов.
- Хранение данных в формате, подходящем для временных рядов (time-series), с низкой кардинальностью для эффективности.
- Визуализация в дашбордах для быстрого анализа.
- Алертs для оперативного реагирования на изменения.

Решение построено на open-source инструментах: Prometheus для хранения метрик и Grafana для визуализации. Сбор данных осуществляется через Bash-скрипт, запускаемый по cron. Развертывание скрипта на серверах происходит через Ansible-роль для автоматизации.

### Ключевые компоненты

1. **Хранилище данных: Prometheus v2.49**
   - Используется для хранения метрик в формате временных рядов.
   - Поддерживает высокую доступность и низкую кардинальность метрик (чтобы избежать перегрузки базы данных).
   - Метрики экспортируются через node-exporter (файлы в формате .prom).

2. **Визуализация: Grafana v11**
   - Дашборды для отображения текущих версий ПО (из меток метрик).
   - Графики для истории изменений (используя числовые метрики и offset для сравнения с предыдущими значениями).
   - Алертs на основе PromQL-запросов для уведомлений о изменениях.

3. **Скрипт сбора данных (Bash)**
   - Запускается по cron (по умолчанию 1 раз в час, настраиваемо).
   - Получает версии ПО на сервере (например, для nginx, openssl и т.д.).
   - Сравнивает с предыдущими значениями из state.json.
   - Генерирует метрики Prometheus.
   - Обновляет state.json и пишет метрики в .prom-файл.
   - Механизм блокировки (lock-file) предотвращает параллельные запуски.
   - Хранит состояние в JSON-файле для отслеживания изменений.

4. **Файл состояния: state.json**
   - Структура: Объект с ключами "apps" (для каждого ПО: current, previous, changes_total, change_time).
   - Используется для детекции изменений и подсчета истории.

5. **Метрики Prometheus**
   - **app_version_info**: Информационная метрика (значение всегда 1). Метки: nodename, appname, version (строка), prev_version (строка). Для отображения "красивой" версии в Grafana. Активна только одна серия на пару {nodename, appname} для низкой кардинальности.
   - **app_version_numeric**: Числовая метрика. Метки: nodename, appname. Значение: Закодированная версия (например, "1.22.1" → 1002200010000). Кодирование: Поддержка до 4 компонентов, удаление pre-release суффиксов, формула v1*1000000000000 + v2*100000000 + v3*10000 + v4.
   - **app_version_change_time_seconds**: Числовая метрика. Метки: nodename, appname. Значение: Unix-time последней смены версии.
   - **Дополнительные метрики**:
     - app_version_scrape_timestamp_seconds: Время последнего сканирования.
     - app_version_collector_success: Успех сбора (0/1).
     - app_version_collector_duration_seconds: Длительность выполнения скрипта.

6. **Развертывание: Ansible-роль**
   - Автоматизирует установку скрипта, cron-задач и node-exporter на целевых серверах.

### Как работает решение

1. **Сбор данных (скрипт)**:
   - Скрипт запускается по cron на каждом сервере.
   - Проверяет lock-file: Если существует, выходит (избегает параллелизма).
   - Читает state.json.
   - Получает текущие версии ПО (например, через команды типа `nginx -v`).
   - Для каждого ПО:
     - Сравнивает с "current" из state.json.
     - Если изменилось: Обновляет previous/current, инкрементирует changes_total, устанавливает change_time.
   - Генерирует метрики (info, numeric, change_time и дополнительные).
   - Атомарно пишет метрики в .prom-файл для node-exporter.
   - Обновляет state.json.
   - Удаляет lock-file.

2. **Хранение и экспорт**:
   - Node-exporter экспортирует .prom-файлы в Prometheus.
   - Prometheus скрейпит метрики периодически.

3. **Визуализация и анализ в Grafana**:
   - Текущие версии: Из меток app_version_info.
   - История изменений: Графики на основе app_version_numeric (с offset для предыдущих значений).
   - Время последнего изменения: PromQL-запросы, например: `time() - last_over_time(timestamp(app_version_numeric != app_version_numeric offset 1h)[1d:])`.
   - Предыдущая версия: Из меток app_version_info.

4. **Алерты**:
   - Любое изменение: `changes(app_version_numeric[2h]) > 0` или `delta(app_version_numeric[2h]) != 0`.
   - Понижение версии: `delta(app_version_numeric[2h]) < 0`.
   - Устаревание данных: `time() - app_version_scrape_timestamp_seconds > 3h`.

### Преимущества (профит)

- **Эффективность**: Низкая кардинальность метрик (только активные серии), что снижает нагрузку на Prometheus.
- **Автоматизация**: Нет нужды в ручном мониторинге; алерты уведомляют о изменениях.
- **Гибкость**: Настраиваемый интервал cron, поддержка множественных ПО, кодирование версий для математических операций (сравнения, delta).
- **Визуализация**: Интуитивные дашборды для быстрого обзора версий и истории.
- **Надежность**: Lock-file предотвращает ошибки, дополнительные метрики мониторят сам скрипт.
- **Масштабируемость**: Легко развернуть на множестве серверов через Ansible.
- **Безопасность**: Не требует установки дополнительных пакетов; работает на стандартных инструментах.
- **Экономия времени**: Автоматическое отслеживание изменений помогает в аудите, compliance и быстром реагировании на уязвимости (например, обновления ПО).

### Архитектурные диаграммы в формате PlantUML

Ниже приведены диаграммы в коде PlantUML. Вы можете скопировать их в инструмент вроде PlantUML.com или IntelliJ с плагином для рендеринга.

#### 1. Общая архитектура (Component Diagram)
Эта диаграмма показывает ключевые компоненты и их взаимодействия.

```
@startuml
skinparam componentStyle rectangle

[Target Server] as Server
[Prometheus] as Prom
[Grafana] as Graf
[Node-Exporter] as NodeExp
[Bash Script] as Script
[state.json] as State
[.prom file] as PromFile
[Ansible Role] as Ansible

Server --> Script : "cron launch"
Script --> State : "read/update"
Script --> PromFile : "write metrics"
NodeExp --> PromFile : "expose"
Prom --> NodeExp : "scrape metrics"
Graf --> Prom : "query data"
Ansible --> Server : "deploy script & cron"

note right of Script
  Collects versions,
  generates metrics,
  handles locks
end note

note bottom of Prom
  Stores time-series
end note

note bottom of Graf
  Dashboards & alerts
end note
@enduml
```

#### 2. Поток работы скрипта (Sequence Diagram)
Эта диаграмма иллюстрирует последовательность действий в скрипте.

```
@startuml
participant "Cron" as Cron
participant "Bash Script" as Script
participant "state.json" as State
participant "Server" as Server
participant ".prom file" as PromFile

Cron -> Script: Launch (hourly)
Script -> Script: Check lock-file (exit if exists)
Script -> State: Read current state
Script -> Server: Get PO versions (e.g., nginx -v)
loop for each app
  Script -> Script: Compare with current
  alt if changed
    Script -> Script: Update previous/current/change_time\nIncrement changes_total
  end
end
Script -> Script: Generate metrics\n(info, numeric, change_time, etc.)
Script -> PromFile: Atomic write metrics
Script -> State: Update JSON
Script -> Script: Remove lock-file
@enduml
```

#### 3. Поток данных от сбора до визуализации (Activity Diagram)
Эта диаграмма показывает общий workflow от сервера до Grafana.

```
@startuml
start
:Deploy script via Ansible;
partition "On Server" {
  :Cron launches script;
  :Collect versions;
  if (Version changed?) then (yes)
    :Update state.json;
    :Generate metrics;
  else (no)
    :Generate metrics;
  endif
  :Write to .prom;
}
:Node-Exporter exposes;
:Prometheus scrapes;
partition "Grafana" {
  :Query Prometheus;
  :Display dashboards;
  :Trigger alerts;
}
stop
@enduml
```